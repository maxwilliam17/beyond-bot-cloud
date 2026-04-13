# ============================================
# BEYOND BOT - CLOUD ENGINE (Headless Chrome)
# ============================================

import time
import os
import random
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================
# HELPER FUNCTIONS
# ============================================

def parse_cookies(cookie_str):
    cookies = []
    for item in cookie_str.split(";"):
        if "=" in item:
            name, value = item.strip().split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".facebook.com"
            })
    return cookies


def safe_click(driver, element):
    try:
        element.click()
        return True
    except:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except:
        pass
    try:
        ActionChains(driver).move_to_element(element).click().perform()
        return True
    except:
        pass
    return False


def scroll_to(driver, element):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.5)
    except:
        pass


def find_element(driver, xpaths, timeout=10):
    if isinstance(xpaths, str):
        xpaths = [xpaths]
    for xpath in xpaths:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        except:
            continue
    return None


def find_clickable(driver, xpaths, timeout=10):
    if isinstance(xpaths, str):
        xpaths = [xpaths]
    for xpath in xpaths:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
        except:
            continue
    return None


def type_slow(element, text, delay=0.05):
    for char in text:
        element.send_keys(char)
        time.sleep(delay)


# ============================================
# CLOUD CHROME SETUP
# ============================================

def setup_driver(settings=None):
    """Setup headless Chrome for cloud deployment"""
    settings = settings or {}

    options = Options()

    # REQUIRED for cloud/Docker
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--single-process")

    # Memory optimization for free tier
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-features=TranslateUI")
    options.add_argument("--js-flags=--max-old-space-size=512")

    # Stealth
    if settings.get("stealth_mode", True):
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        print("🥷 Stealth mode enabled")

    # Suppress logs
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument("--log-level=3")

    # Use system Chrome
    chrome_bin = os.environ.get('CHROME_BIN', '/usr/bin/google-chrome-stable')
    if os.path.exists(chrome_bin):
        options.binary_location = chrome_bin

    # Setup service
    chromedriver_path = '/usr/local/bin/chromedriver'
    if os.path.exists(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
    else:
        # Fallback to webdriver-manager
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)

    # Anti-detection
    if settings.get("stealth_mode", True):
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = {runtime: {}};
            """
        })

    return driver


# ============================================
# ACCOUNT HEALTH CHECK
# ============================================

def check_account_health(cookie_string):
    """Test if Facebook cookies are still valid"""
    print("\n🏥 Starting Account Health Check...")
    driver = None

    try:
        driver = setup_driver({"stealth_mode": True})

        print("   🌐 Opening Facebook...")
        driver.get("https://www.facebook.com")
        time.sleep(3)

        print("   🍪 Adding cookies...")
        for c in parse_cookies(cookie_string):
            try:
                driver.add_cookie(c)
            except:
                pass

        driver.refresh()
        time.sleep(5)

        url = driver.current_url.lower()

        if "login" in url or "checkpoint" in url:
            print("   ❌ Cookies invalid!")
            return {
                "status": "invalid",
                "logged_in": False,
                "marketplace_access": False,
                "account_name": None
            }

        # Check marketplace
        print("   🛒 Checking Marketplace...")
        driver.get("https://www.facebook.com/marketplace")
        time.sleep(4)

        marketplace_ok = "marketplace" in driver.current_url.lower()

        status = "healthy" if marketplace_ok else "limited"
        print(f"   {'✅' if marketplace_ok else '⚠️'} Status: {status}")

        return {
            "status": status,
            "logged_in": True,
            "marketplace_access": marketplace_ok,
            "account_name": "Verified"
        }

    except Exception as e:
        print(f"   ❌ Health check error: {e}")
        return {
            "status": "error",
            "logged_in": False,
            "marketplace_access": False,
            "account_name": None
        }
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


# ============================================
# POST SINGLE LISTING
# ============================================

def post_single_listing(driver, wait, listing, num, settings):
    """Post one listing to Facebook Marketplace"""

    print(f"\n{'='*60}")
    print(f"📦 LISTING #{num}: {listing['title'][:45]}...")
    print(f"   💰 ${listing['price']} | 📁 {listing.get('category', 'Household')}")
    print(f"   🖼️ {len(listing.get('images', []))} image(s)")
    print(f"{'='*60}")

    try:
        # Navigate
        print("\n🌐 Opening Marketplace create page...")
        driver.get("https://www.facebook.com/marketplace/create/item")
        time.sleep(random.uniform(4, 7))

        if "login" in driver.current_url.lower():
            print("   ❌ Not logged in!")
            return {"status": "failed", "title": listing["title"], "error": "Login required"}

        # 1. IMAGE
        if listing.get("images"):
            print("\n📷 Uploading image...")
            try:
                valid_images = [
                    os.path.abspath(img) for img in listing["images"]
                    if img and os.path.exists(img)
                ]
                if valid_images:
                    file_input = driver.find_element(By.XPATH, "//input[@type='file']")
                    file_input.send_keys("\n".join(valid_images))
                    time.sleep(4)
                    print(f"   ✅ Image uploaded")
                else:
                    print("   ⚠️ No valid images found")
            except Exception as e:
                print(f"   ⚠️ Image error: {str(e)[:40]}")

        time.sleep(1)

        # 2. TITLE
        print("\n📝 Title...")
        try:
            title_el = find_clickable(driver, [
                "//label[@aria-label='Title']//input",
                "//span[text()='Title']/ancestor::label//input",
                "//input[contains(@aria-label, 'Title')]",
            ], 10)

            if title_el:
                title_el.clear()
                time.sleep(0.2)
                type_slow(title_el, listing["title"], 0.03)
                print(f"   ✅ {listing['title'][:35]}...")
            else:
                print("   ❌ Title field not found")
        except Exception as e:
            print(f"   ⚠️ Title: {str(e)[:30]}")

        time.sleep(0.5)

        # 3. PRICE
        print("\n💰 Price...")
        try:
            price_el = find_element(driver, [
                "//label[@aria-label='Price']//input",
                "//span[text()='Price']/ancestor::label//input",
            ], 8)
            if price_el:
                price_el.clear()
                price_el.send_keys(str(listing["price"]))
                print(f"   ✅ ${listing['price']}")
        except Exception as e:
            print(f"   ⚠️ Price: {str(e)[:30]}")

        time.sleep(0.5)

        # 4. CATEGORY
        category = listing.get("category", "Household")
        print(f"\n📁 Category: {category}...")
        try:
            cat_dropdown = find_clickable(driver, [
                "//label[@aria-label='Category']",
                "//span[text()='Category']/ancestor::label",
            ], 5)
            if cat_dropdown:
                scroll_to(driver, cat_dropdown)
                safe_click(driver, cat_dropdown)
                time.sleep(1.5)

                cat_option = find_clickable(driver, [
                    f"//span[text()='{category}']",
                    f"//div[@role='option']//span[text()='{category}']",
                    "//span[text()='Household']",
                ], 5)
                if cat_option:
                    safe_click(driver, cat_option)
                    print(f"   ✅ {category}")
        except Exception as e:
            print(f"   ⚠️ Category: {str(e)[:30]}")

        time.sleep(1)

        # 5. CONDITION
        condition = listing.get("condition", "New")
        print(f"\n🏷️ Condition: {condition}...")
        try:
            cond_dropdown = find_clickable(driver, [
                "//label[@aria-label='Condition']",
                "//span[text()='Condition']/ancestor::label",
            ], 5)
            if cond_dropdown:
                scroll_to(driver, cond_dropdown)
                safe_click(driver, cond_dropdown)
                time.sleep(1.5)

                fb_cond = {
                    "New": "New",
                    "Used - Like New": "Used - like new",
                    "Used - Good": "Used - good",
                    "Used - Fair": "Used - fair",
                }.get(condition, "New")

                cond_option = find_clickable(driver, [
                    f"//span[contains(text(), '{fb_cond}')]",
                    f"//div[@role='option']//span[contains(text(), '{fb_cond}')]",
                    "//span[text()='New']",
                ], 5)
                if cond_option:
                    safe_click(driver, cond_option)
                    print(f"   ✅ {condition}")
        except Exception as e:
            print(f"   ⚠️ Condition: {str(e)[:30]}")

        time.sleep(1)

        # 6. DESCRIPTION
        desc = listing.get("description", "")
        if desc:
            print(f"\n📄 Description ({len(desc)} chars)...")
            try:
                desc_el = find_element(driver, [
                    "//label[@aria-label='Description']//textarea",
                    "//span[text()='Description']/ancestor::label//textarea",
                    "//textarea[contains(@aria-label, 'Description')]",
                    "//label[contains(@aria-label, 'escription')]//textarea",
                ], 8)

                if desc_el:
                    scroll_to(driver, desc_el)
                    safe_click(driver, desc_el)
                    time.sleep(0.5)

                    desc_el.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.1)
                    desc_el.send_keys(Keys.BACKSPACE)
                    time.sleep(0.3)

                    try:
                        desc_el.send_keys(desc)
                        print(f"   ✅ Description filled")
                    except:
                        for char in desc:
                            desc_el.send_keys(char)
                            time.sleep(0.01)
                        print(f"   ✅ Description filled (slow)")
                else:
                    print("   ⚠️ Description field not found")
            except Exception as e:
                print(f"   ⚠️ Description: {str(e)[:40]}")

        time.sleep(1)

        # 7. LOCATION
        location = listing.get("location", "")
        if location:
            print(f"\n📍 Location: {location}...")
            try:
                loc_el = find_clickable(driver, [
                    "//label[@aria-label='Location']//input",
                    "//span[text()='Location']/ancestor::label//input",
                ], 5)
                if loc_el:
                    scroll_to(driver, loc_el)
                    safe_click(driver, loc_el)
                    time.sleep(0.5)

                    loc_el.send_keys(Keys.CONTROL + "a")
                    loc_el.send_keys(Keys.BACKSPACE)
                    time.sleep(0.5)

                    type_slow(loc_el, location, 0.1)
                    time.sleep(2.5)

                    loc_el.send_keys(Keys.ARROW_DOWN)
                    time.sleep(0.3)
                    loc_el.send_keys(Keys.ENTER)
                    time.sleep(1)
                    print(f"   ✅ Location set")
            except Exception as e:
                print(f"   ⚠️ Location: {str(e)[:30]}")

        time.sleep(2)

        # 8. NEXT BUTTON
        print("\n➡️ Checking for Next button...")
        try:
            next_btn = find_clickable(driver, [
                "//div[@aria-label='Next']",
                "//span[text()='Next']/ancestor::div[@role='button']",
                "//div[@role='button']//span[text()='Next']/..",
            ], 5)
            if next_btn:
                scroll_to(driver, next_btn)
                safe_click(driver, next_btn)
                time.sleep(3)
                print("   ✅ Next clicked")
            else:
                print("   ℹ️ No Next button")
        except:
            print("   ℹ️ No Next button found")

        # 9. PUBLISH
        print("\n🚀 Publishing...")
        try:
            pub_btn = find_clickable(driver, [
                "//div[@aria-label='Publish']",
                "//span[text()='Publish']/ancestor::div[@role='button']",
                "//div[@role='button']//span[text()='Publish']/..",
                "//div[@aria-label='Publish'][@role='button']",
            ], 10)

            if pub_btn:
                scroll_to(driver, pub_btn)
                time.sleep(0.5)
                safe_click(driver, pub_btn)
                time.sleep(6)
                print("   ✅ Published successfully!")
            else:
                print("   ❌ Publish button not found")
                return {
                    "status": "failed",
                    "title": listing["title"],
                    "error": "Publish button not found"
                }
        except Exception as e:
            print(f"   ❌ Publish failed: {str(e)[:30]}")
            return {"status": "failed", "title": listing["title"], "error": str(e)}

        print(f"\n✅ LISTING #{num} COMPLETED!")
        return {"status": "success", "title": listing["title"]}

    except Exception as e:
        print(f"\n❌ LISTING #{num} FAILED: {str(e)[:60]}")
        return {"status": "failed", "title": listing["title"], "error": str(e)}


# ============================================
# MAIN BOT FUNCTION (CLOUD)
# ============================================

def run_facebook_bot_multiple(data, progress_callback=None):
    """Main bot function for cloud deployment"""
    settings = data.get("advanced_settings", {})
    # Force headless in cloud
    settings["headless_mode"] = True
    settings["stealth_mode"] = True

    driver = None
    results = []

    try:
        print("\n🌐 Setting up headless Chrome...")
        driver = setup_driver(settings)
        wait = WebDriverWait(driver, 20)
        print("   ✅ Browser ready")

        # Login
        print("\n🔐 Logging into Facebook...")
        driver.get("https://www.facebook.com")
        time.sleep(4)

        cookies = parse_cookies(data["cookie_string"])
        for c in cookies:
            try:
                driver.add_cookie(c)
            except:
                pass

        driver.refresh()
        time.sleep(6)

        # Verify login
        try:
            wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[@aria-label='Account' or @aria-label='Your profile']"
            )))
            print("✅ Logged in successfully!")
        except:
            print("⚠️ Login verification unclear, continuing...")

        # Post listings
        total = len(data["listings"])
        print(f"\n📋 Posting {total} listings...")

        for i, listing in enumerate(data["listings"], 1):
            # Check stop signal
            try:
                from app import bot_state
                if not bot_state.get("is_running", True):
                    print("⏹️ Stop signal received!")
                    break
            except:
                pass

            # Update progress
            if progress_callback:
                progress_callback(i, total, listing.get("title", ""))

            result = post_single_listing(driver, wait, listing, i, settings)
            results.append(result)

            # Delay between posts
            if i < total:
                delay = random.uniform(
                    settings.get("min_delay", 10),
                    settings.get("max_delay", 20)
                )
                print(f"\n⏳ Waiting {delay:.0f}s before next listing...")
                time.sleep(delay)

        # Summary
        ok = sum(1 for r in results if r["status"] == "success")
        print(f"\n{'='*50}")
        print(f"📊 RESULTS: {ok}/{total} successful")
        print(f"{'='*50}")

    except Exception as e:
        print(f"\n❌ BOT ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            print("\n🏁 Closing browser...")
            try:
                driver.quit()
            except:
                pass

    return results