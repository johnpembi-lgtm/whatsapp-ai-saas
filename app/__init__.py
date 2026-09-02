import os
from flask import Flask
from flask_apscheduler import APScheduler
from config import Config

scheduler = APScheduler()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validation stricte en production. Les configurations de test peuvent
    # définir TESTING=True et fournir des valeurs factices sans dépendre du .env.
    if not app.config.get("TESTING") and hasattr(config_class, "validate"):
        config_class.validate()

    app.json.ensure_ascii = False

    # Desactiver le scheduler pendant l'exécution des tests
    if not app.config.get("TESTING"):
        scheduler.init_app(app)

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
                scheduler.start()

    from app.routes.admin_routes import admin_bp
    from app.routes.webhook_routes import webhook_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)

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