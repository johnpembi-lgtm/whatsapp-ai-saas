import os
from flask import Flask
from flask_apscheduler import APScheduler
from config import Config

scheduler = APScheduler()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validation stricte en production
    if not app.config.get("TESTING") and hasattr(config_class, "validate"):
        config_class.validate()

    app.json.ensure_ascii = False

    # Protection contre la réinitialisation si le scheduler tourne déjà ou si TESTING est actif
    is_testing = app.config.get("TESTING", False) or os.environ.get("FLASK_ENV") == "testing"
    
    if not is_testing:
        if not scheduler.running:
            try:
                scheduler.init_app(app)
            except Exception:
                pass  # Évite les erreurs de configuration si init_app est appelé plusieurs fois

        if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            from app.services.retargeting_service import RetargetingService

            if not scheduler.get_job("retargeting_job"):
                scheduler.add_job(
                    id="retargeting_job",
                    func=RetargetingService.process_abandoned_carts,
                    trigger="interval",
                    minutes=15,
                    max_instances=1,
                    coalesce=True,
                )

            if not scheduler.running:
                try:
                    scheduler.start()
                except Exception:
                    pass

    # Enregistrement des Blueprints
    from app.routes.admin_routes import admin_bp
    from app.routes.webhook_routes import webhook_bp
    from app.routes.orders_routes import orders_bp
    from app.routes.handover_routes import handover_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(handover_bp)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.route("/", methods=["GET"])
    def home():
        return {"status": "ok", "service": "PEMBI Backend"}, 200

    return app