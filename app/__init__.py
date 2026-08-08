from flask import Flask
from flask_apscheduler import APScheduler
from config import Config
from app.core.database import init_db

scheduler = APScheduler()


def create_app(config_class=Config):
    """Factory Function pour initialiser l'application Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Désactive l'encodage ASCII pour afficher proprement les accents (é, è, à)
    app.json.ensure_ascii = False

    # Initialisation de la base de données SQLite à l'allumage du serveur
    init_db()

    # Planificateur de tâches pour les relances automatiques
    app.config["SCHEDULER_API_ENABLED"] = True
    scheduler.init_app(app)
    scheduler.start()

    # Exécution de la tâche de relance toutes les 30 minutes
    @scheduler.task("interval", id="run_retargeting", minutes=30)
    def scheduled_retargeting():
        with app.app_context():
            from app.services.retargeting_service import RetargetingService
            RetargetingService.process_abandoned_carts()

    # Enregistrement des Blueprints (Routes)
    from app.routes.webhook_routes import webhook_bp
    from app.routes.admin_routes import admin_bp

    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)

    @app.route("/", methods=["GET"])
    def home():
        """Route racine par défaut pour éviter les erreurs 404 dans le navigateur"""
        return {"status": "ok", "service": "WhatsAuto IA Backend"}, 200

    @app.route("/health", methods=["GET"])
    def health_check():
        """Route simple pour vérifier que le serveur tourne bien"""
        return {"status": "ok", "service": "WhatsAuto IA Backend"}, 200

    return app