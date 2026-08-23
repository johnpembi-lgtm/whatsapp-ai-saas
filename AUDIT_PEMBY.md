# Audit technique — Whatsapp Saas
### Sécurité

- suppression de la clé Flask de secours codée en dur ;
- suppression du mot de passe administrateur par défaut ;
- validation au démarrage des variables sensibles obligatoires ;
- `APP_SECRET` Meta obligatoire pour accepter un webhook entrant ;
- API REST de Flask-APScheduler désactivée ;
- protection CSRF ajoutée au formulaire d'ajout de boutique ;
- cookies de session `HttpOnly`, `SameSite=Lax` et `Secure` par défaut ;
- en-têtes `X-Content-Type-Options`, `X-Frame-Options` et `Referrer-Policy` ;
- suppression des fragments de token WhatsApp dans les logs ;
- refus explicite d'un envoi WhatsApp si aucun token n'est disponible.

### Webhook / traitement des messages

- pool de workers borné pour le traitement des messages au lieu de créer un thread sans limite par message ;
- déduplication existante conservée ;
- normalisation des numéros pour identifier correctement le vendeur ;
- historique IA récupéré avant l'enregistrement du message courant : le dernier message n'est plus injecté deux fois dans le prompt ;
- le tag technique `[SEND_IMAGE: ...]` n'est plus stocké dans l'historique ;
- repli sur un message texte si l'envoi de l'image échoue.

### Retargeting

- correction du test de retour de `WhatsAppService.send_message()` : le service renvoie un booléen et non une réponse JSON ;
- suppression de la dépendance à `current_app` dans le job planifié ;
- un envoi réussi fait maintenant correctement avancer le statut du panier ;
- `max_instances=1` et `coalesce=True` ajoutés au job ;
- `Procfile` ramené à un seul worker Gunicorn pour éviter plusieurs schedulers simultanés.

### Données / intégrations

- remplacement des chaînes `"now()"` par des timestamps UTC ISO réels avant envoi à Supabase ;
- version Meta Graph API utilisée par les messages et médias centralisée via `META_API_VERSION` ;
- vérification de la présence de l'URL de téléchargement média Meta ;
- un message vendeur n'est stocké comme réponse assistant que si l'envoi au client a réellement réussi ;
- activation du mode humain renvoie maintenant un échec si Supabase n'a pas pu enregistrer l'état.

### Dépendances et tests

- `requirements.txt` converti de UTF-16 vers UTF-8/ASCII, compatible avec `pip install -r requirements.txt` dans Docker/Linux ;
- ajout explicite de `httpx` ;
- script Gemini migré vers `google-genai` ;
- `pytest.ini` limite la collecte aux tests automatisés du dossier `tests/` et exclut les scripts de test manuels ;
- compilation Python de l'ensemble du projet vérifiée après corrections.

## Variables minimales

Copier `.env.example` vers `.env` et définir au minimum :

- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `WEBHOOK_VERIFY_TOKEN`
- `APP_SECRET`
- `SUPABASE_URL`
- `SUPABASE_KEY`

Puis compléter les clés WhatsApp, Groq, Google Sheets et ImgBB selon les fonctions utilisées.
