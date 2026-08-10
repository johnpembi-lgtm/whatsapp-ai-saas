from flask import Flask
from flask_apscheduler import APScheduler
from config import Config

scheduler = APScheduler()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Clé secrète obligatoire pour les messages flash
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "une_cle_secrete_ultra_securisee_2026"

    app.json.ensure_ascii = False

    # Planificateur
    app.config["SCHEDULER_API_ENABLED"] = True
    scheduler.init_app(app)
    if not scheduler.running:
        scheduler.start()

    # Blueprints
    from app.routes.admin_routes import admin_bp
    from app.routes.webhook_routes import webhook_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)

    @app.route("/", methods=["GET"])
    def home():
        return {"status": "ok", "service": "WhatsAuto IA Backend"}, 200

    return app