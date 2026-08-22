import os
from flask import Flask
from flask_apscheduler import APScheduler
from config import Config

scheduler = APScheduler()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = "une_cle_secrete_ultra_securisee_2026"

    app.json.ensure_ascii = False

    # Configuration et démarrage du Scheduler
    app.config["SCHEDULER_API_ENABLED"] = True
    scheduler.init_app(app)

    # Évite le double démarrage en mode Reload de Flask
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from app.services.retargeting_service import RetargetingService

        if not scheduler.get_job("retargeting_job"):
            scheduler.add_job(
                id="retargeting_job",
                func=RetargetingService.process_abandoned_carts,
                trigger="interval",
                minutes=15
            )
        
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