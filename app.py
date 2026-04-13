# ============================================
# BEYOND BOT CLOUD - Web Dashboard + API
# ============================================

import os
import sys
import json
import threading
import time
import queue
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, send_from_directory
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Local imports
from config_manager import (
    load_config, save_config, DEFAULT_CONFIG,
    load_accounts, add_account, delete_account,
    get_account_cookies, get_account_names,
    update_last_used, get_stats_summary, reset_stats,
    add_posting_session, update_account_cookies
)
from combination_manager import (
    load_listings_from_csv, generate_unique_combinations,
    save_used_combinations, get_combination_stats,
    reset_account_combinations, validate_csv_file,
    get_all_accounts_stats
)

# ============================================
# APP SETUP
# ============================================

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'beyond-bot-secret-key-change-me')
CORS(app)

# Global state
bot_state = {
    "is_running": False,
    "current_task": None,
    "progress": 0,
    "total": 0,
    "completed": 0,
    "success": 0,
    "failed": 0,
    "current_listing": "",
    "logs": [],
    "last_run": None,
    "account": "",
    "error": None
}

log_lock = threading.Lock()
MAX_LOGS = 500

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PHOTOS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
DATA_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

for folder in [UPLOAD_FOLDER, PHOTOS_FOLDER, DATA_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# ============================================
# AUTH
# ============================================

BOT_PASSWORD = os.environ.get('BOT_PASSWORD', 'admin123')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.is_json:
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ============================================
# LOGGING
# ============================================

def bot_log(message, level="info"):
    """Add log entry"""
    with log_lock:
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": message,
            "level": level
        }
        bot_state["logs"].append(entry)
        if len(bot_state["logs"]) > MAX_LOGS:
            bot_state["logs"] = bot_state["logs"][-MAX_LOGS:]
        print(f"[{entry['time']}] [{level.upper()}] {message}")


# ============================================
# ROUTES - AUTH
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == BOT_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template('dashboard.html', page='login', error='Wrong password')
    return render_template('dashboard.html', page='login')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============================================
# ROUTES - PAGES
# ============================================

@app.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    stats = get_stats_summary()
    config = load_config()
    accounts = get_account_names()
    return render_template('dashboard.html',
        page='dashboard',
        stats=stats,
        config=config,
        accounts=accounts,
        bot_state=bot_state
    )


# ============================================
# ROUTES - API
# ============================================

@app.route('/api/status')
@login_required
def api_status():
    """Get current bot status"""
    return jsonify({
        "is_running": bot_state["is_running"],
        "progress": bot_state["progress"],
        "total": bot_state["total"],
        "completed": bot_state["completed"],
        "success": bot_state["success"],
        "failed": bot_state["failed"],
        "current_listing": bot_state["current_listing"],
        "account": bot_state["account"],
        "error": bot_state["error"],
        "last_run": bot_state["last_run"]
    })


@app.route('/api/logs')
@login_required
def api_logs():
    """Get recent logs"""
    since = request.args.get('since', 0, type=int)
    with log_lock:
        logs = bot_state["logs"][since:]
    return jsonify({"logs": logs, "total": len(bot_state["logs"])})


@app.route('/api/stats')
@login_required
def api_stats():
    """Get posting statistics"""
    return jsonify(get_stats_summary())


# ============================================
# ROUTES - ACCOUNTS
# ============================================

@app.route('/api/accounts', methods=['GET'])
@login_required
def api_get_accounts():
    """Get all accounts"""
    accounts = load_accounts()
    account_list = []
    config = load_config()

    csv_file = config.get("listings_csv_file", "")
    photos_folder = config.get("images_folder", "")

    csv_listings = load_listings_from_csv(csv_file) if csv_file else []
    photos = []
    if photos_folder and os.path.exists(photos_folder):
        exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
        photos = [os.path.join(photos_folder, f) for f in sorted(os.listdir(photos_folder)) if f.lower().endswith(exts)]

    for name, data in accounts.items():
        combo_stats = get_combination_stats(name, len(csv_listings), len(photos)) if csv_listings and photos else {}
        account_list.append({
            "name": name,
            "added_date": data.get("added_date", ""),
            "last_used": data.get("last_used", ""),
            "status": data.get("status", "active"),
            "combinations": combo_stats
        })

    return jsonify({"accounts": account_list, "selected": config.get("selected_account", "")})


@app.route('/api/accounts', methods=['POST'])
@login_required
def api_add_account():
    """Add new account"""
    data = request.get_json()
    name = data.get('name', '').strip()
    cookies = data.get('cookies', '').strip()

    if not name:
        return jsonify({"error": "Name required"}), 400
    if not cookies or len(cookies) < 50:
        return jsonify({"error": "Valid cookies required"}), 400

    if add_account(name, cookies):
        bot_log(f"👤 Account added: {name}", "success")
        return jsonify({"success": True, "message": f"Account '{name}' added"})
    return jsonify({"error": "Failed to add account"}), 500


@app.route('/api/accounts/<name>', methods=['DELETE'])
@login_required
def api_delete_account(name):
    """Delete account"""
    if delete_account(name):
        reset_account_combinations(name)
        bot_log(f"🗑️ Account deleted: {name}", "warning")
        return jsonify({"success": True})
    return jsonify({"error": "Failed to delete"}), 500


@app.route('/api/accounts/<name>/select', methods=['POST'])
@login_required
def api_select_account(name):
    """Select active account"""
    cookies = get_account_cookies(name)
    if not cookies:
        return jsonify({"error": "Account not found"}), 404

    config = load_config()
    config["selected_account"] = name
    save_config(config)
    update_last_used(name)

    bot_state["account"] = name
    bot_log(f"👤 Selected account: {name}", "info")
    return jsonify({"success": True, "account": name})


@app.route('/api/accounts/<name>/cookies', methods=['PUT'])
@login_required
def api_update_cookies(name):
    """Update account cookies"""
    data = request.get_json()
    cookies = data.get('cookies', '').strip()

    if not cookies or len(cookies) < 50:
        return jsonify({"error": "Valid cookies required"}), 400

    if update_account_cookies(name, cookies):
        bot_log(f"🍪 Cookies updated: {name}", "success")
        return jsonify({"success": True})
    return jsonify({"error": "Failed to update"}), 500


@app.route('/api/accounts/<name>/reset-combos', methods=['POST'])
@login_required
def api_reset_combos(name):
    """Reset combinations for account"""
    reset_account_combinations(name)
    bot_log(f"🔄 Combinations reset: {name}", "info")
    return jsonify({"success": True})


# ============================================
# ROUTES - DATA SOURCES
# ============================================

@app.route('/api/csv/upload', methods=['POST'])
@login_required
def api_upload_csv():
    """Upload CSV file"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith('.csv'):
        return jsonify({"error": "Only CSV files allowed"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    validation = validate_csv_file(filepath)
    if not validation["valid"]:
        os.remove(filepath)
        return jsonify({"error": f"Invalid CSV: {validation['errors']}"}), 400

    listings = load_listings_from_csv(filepath)

    config = load_config()
    config["listings_csv_file"] = filepath
    save_config(config)

    bot_log(f"📋 CSV uploaded: {len(listings)} listings", "success")
    return jsonify({
        "success": True,
        "listings_count": len(listings),
        "columns": validation["columns"],
        "filename": filename
    })


@app.route('/api/csv/info')
@login_required
def api_csv_info():
    """Get current CSV info"""
    config = load_config()
    csv_file = config.get("listings_csv_file", "")

    if csv_file and os.path.exists(csv_file):
        listings = load_listings_from_csv(csv_file)
        return jsonify({
            "loaded": True,
            "file": os.path.basename(csv_file),
            "count": len(listings),
            "preview": listings[:3]
        })
    return jsonify({"loaded": False})


@app.route('/api/photos/upload', methods=['POST'])
@login_required
def api_upload_photos():
    """Upload photos"""
    if 'files' not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist('files')
    saved = 0
    exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')

    for file in files:
        if file.filename and file.filename.lower().endswith(exts):
            filename = secure_filename(file.filename)
            file.save(os.path.join(PHOTOS_FOLDER, filename))
            saved += 1

    config = load_config()
    config["images_folder"] = PHOTOS_FOLDER
    save_config(config)

    bot_log(f"🖼️ {saved} photos uploaded", "success")
    return jsonify({"success": True, "count": saved})


@app.route('/api/photos/info')
@login_required
def api_photos_info():
    """Get photos info"""
    config = load_config()
    folder = config.get("images_folder", PHOTOS_FOLDER)

    if folder and os.path.exists(folder):
        exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
        photos = [f for f in os.listdir(folder) if f.lower().endswith(exts)]
        return jsonify({"loaded": True, "count": len(photos), "folder": folder})
    return jsonify({"loaded": False, "count": 0})


# ============================================
# ROUTES - BOT CONTROL
# ============================================

@app.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    """Generate listing combinations"""
    data = request.get_json()
    count = data.get('count', 5)
    account = data.get('account', '')

    if not account:
        config = load_config()
        account = config.get("selected_account", "")

    if not account:
        return jsonify({"error": "No account selected"}), 400

    config = load_config()
    csv_file = config.get("listings_csv_file", "")
    photos_folder = config.get("images_folder", PHOTOS_FOLDER)

    if not csv_file or not os.path.exists(csv_file):
        return jsonify({"error": "No CSV file loaded"}), 400

    csv_listings = load_listings_from_csv(csv_file)
    if not csv_listings:
        return jsonify({"error": "No listings in CSV"}), 400

    exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    photos = []
    if photos_folder and os.path.exists(photos_folder):
        photos = [os.path.join(photos_folder, f) for f in sorted(os.listdir(photos_folder)) if f.lower().endswith(exts)]

    if not photos:
        return jsonify({"error": "No photos available"}), 400

    combinations, stats = generate_unique_combinations(
        account, csv_listings, photos, count, allow_repeats=True
    )

    if not combinations:
        return jsonify({"error": stats.get("error", "Failed to generate")}), 400

    # Store in session/state for posting
    preview = []
    for combo in combinations:
        preview.append({
            "title": combo["listing"].get("title", ""),
            "price": combo["listing"].get("price", "0"),
            "category": combo["listing"].get("category", "Household"),
            "condition": combo["listing"].get("condition", "New"),
            "location": combo["listing"].get("location", ""),
            "description": combo["listing"].get("description", ""),
            "photo": os.path.basename(combo.get("photo", "")),
            "is_repeated": combo.get("is_repeated", False),
            "key": combo.get("key", "")
        })

    # Store combinations globally for posting
    bot_state["pending_combinations"] = combinations
    bot_state["pending_preview"] = preview

    bot_log(f"🎲 Generated {len(combinations)} listings for {account}", "info")

    return jsonify({
        "success": True,
        "count": len(combinations),
        "preview": preview,
        "stats": stats
    })


@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    """Start posting bot"""
    if bot_state["is_running"]:
        return jsonify({"error": "Bot is already running"}), 400

    data = request.get_json() or {}
    account = data.get('account', '')

    if not account:
        config = load_config()
        account = config.get("selected_account", "")

    if not account:
        return jsonify({"error": "No account selected"}), 400

    cookies = get_account_cookies(account)
    if not cookies:
        return jsonify({"error": "No cookies for this account"}), 400

    combinations = bot_state.get("pending_combinations", [])
    if not combinations:
        return jsonify({"error": "No listings generated. Generate first!"}), 400

    config = load_config()
    settings = config.get("advanced_settings", DEFAULT_CONFIG["advanced_settings"])
    location = data.get('location', config.get("default_location", "Laval, Quebec"))

    # Prepare listings
    listings_data = []
    for combo in combinations:
        listing = combo["listing"].copy()
        if not listing.get("location"):
            listing["location"] = location
        listing["images"] = [combo["photo"]] if combo.get("photo") else []
        listings_data.append(listing)

    bot_data = {
        "cookie_string": cookies,
        "listings": listings_data,
        "advanced_settings": settings,
        "account_name": account,
        "combinations": combinations
    }

    # Start bot in background thread
    thread = threading.Thread(target=run_bot_thread, args=(bot_data,), daemon=True)
    thread.start()

    bot_log(f"🚀 Bot started: {len(listings_data)} listings for {account}", "success")
    return jsonify({"success": True, "message": "Bot started!"})


@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    """Stop the bot"""
    bot_state["is_running"] = False
    bot_log("⏹️ Stop requested", "warning")
    return jsonify({"success": True, "message": "Stop signal sent"})


@app.route('/api/settings', methods=['GET'])
@login_required
def api_get_settings():
    """Get settings"""
    config = load_config()
    return jsonify({
        "settings": config.get("advanced_settings", DEFAULT_CONFIG["advanced_settings"]),
        "default_location": config.get("default_location", "Laval, Quebec"),
        "theme": config.get("theme", "light")
    })


@app.route('/api/settings', methods=['POST'])
@login_required
def api_save_settings():
    """Save settings"""
    data = request.get_json()
    config = load_config()

    if 'settings' in data:
        config["advanced_settings"] = data["settings"]
    if 'default_location' in data:
        config["default_location"] = data["default_location"]

    save_config(config)
    bot_log("⚙️ Settings saved", "info")
    return jsonify({"success": True})


@app.route('/api/stats/reset', methods=['POST'])
@login_required
def api_reset_stats():
    """Reset all statistics"""
    reset_stats()
    bot_log("📊 Statistics reset", "warning")
    return jsonify({"success": True})


# ============================================
# KEEP ALIVE ENDPOINT (for UptimeRobot)
# ============================================

@app.route('/health')
def health():
    return jsonify({
        "status": "alive",
        "bot_running": bot_state["is_running"],
        "uptime": "ok",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/ping')
def ping():
    return "pong", 200


# ============================================
# BOT RUNNER THREAD
# ============================================

def run_bot_thread(bot_data):
    """Run the bot in a background thread"""
    import bot_engine

    account = bot_data["account_name"]
    combinations = bot_data.get("combinations", [])
    total = len(bot_data["listings"])

    bot_state["is_running"] = True
    bot_state["progress"] = 0
    bot_state["total"] = total
    bot_state["completed"] = 0
    bot_state["success"] = 0
    bot_state["failed"] = 0
    bot_state["account"] = account
    bot_state["error"] = None
    bot_state["current_listing"] = ""

    try:
        # Override print to capture logs
        import builtins
        original_print = builtins.print

        def custom_print(*args, **kwargs):
            message = " ".join(str(a) for a in args)
            bot_log(message)
            original_print(*args, **kwargs)

        builtins.print = custom_print

        # Run bot
        results = bot_engine.run_facebook_bot_multiple(
            bot_data,
            progress_callback=update_bot_progress
        )

        builtins.print = original_print

        # Calculate results
        ok = sum(1 for r in results if r.get("status") == "success")
        failed = total - ok

        # Save stats
        titles = [r.get("title", "") for r in results]
        add_posting_session(account, total, ok, failed, titles)

        # Save used combinations
        if combinations:
            successful_combos = []
            for i, result in enumerate(results):
                if result.get("status") == "success" and i < len(combinations):
                    combo = combinations[i]
                    if not combo.get("is_repeated", False):
                        successful_combos.append(combo)
            if successful_combos:
                save_used_combinations(account, successful_combos)

        bot_state["success"] = ok
        bot_state["failed"] = failed
        bot_state["progress"] = 100
        bot_state["last_run"] = datetime.now().isoformat()

        bot_log(f"✅ Completed: {ok}/{total} successful", "success")

    except Exception as e:
        bot_state["error"] = str(e)
        bot_log(f"❌ Bot error: {e}", "error")
        import traceback
        traceback.print_exc()
    finally:
        bot_state["is_running"] = False
        bot_state["current_listing"] = ""
        bot_state["pending_combinations"] = []
        bot_state["pending_preview"] = []


def update_bot_progress(current, total, listing_title=""):
    """Callback for bot progress updates"""
    bot_state["completed"] = current
    bot_state["total"] = total
    bot_state["progress"] = int((current / total) * 100) if total > 0 else 0
    bot_state["current_listing"] = listing_title


# ============================================
# FIREBASE INIT
# ============================================

def init_firebase():
    """Initialize Firebase on startup"""
    try:
        cred_json = os.environ.get('FIREBASE_CREDENTIALS', '')

        if cred_json and cred_json.strip().startswith('{'):
            # JSON string in env var
            cred_path = os.path.join(DATA_FOLDER, 'firebase_creds.json')
            with open(cred_path, 'w') as f:
                f.write(cred_json)

            from firebase_manager import get_firebase_manager
            firebase = get_firebase_manager()
            if firebase.initialize(cred_path):
                bot_log("🔥 Firebase connected", "success")
                return True

        # Try auto-init from config
        from firebase_manager import get_firebase_manager
        firebase = get_firebase_manager()
        if firebase.auto_initialize():
            bot_log("🔥 Firebase auto-connected", "success")
            return True

        bot_log("⚠️ Firebase not configured", "warning")
        return False

    except Exception as e:
        bot_log(f"⚠️ Firebase init error: {e}", "warning")
        return False


# ============================================
# STARTUP
# ============================================

# Initialize on startup
with app.app_context():
    bot_log("🤖 Beyond Bot Cloud starting...", "info")
    init_firebase()

    config = load_config()
    selected = config.get("selected_account", "")
    if selected:
        bot_state["account"] = selected
        bot_log(f"👤 Loaded account: {selected}", "info")

    bot_log("✅ Beyond Bot Cloud ready!", "success")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)