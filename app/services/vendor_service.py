"""
Traite tous les messages provenant du vendeur (is_vendor == True).

Règle d'or (voir doc d'architecture) : un message du vendeur ne doit JAMAIS
être transmis au traitement client standard (AIService côté client). Ce
module est le point d'entrée unique pour tout ce que le vendeur peut faire :
commandes slash (/stock, /prix, /mode...), relais vers un client en
HUMAN_MODE, et ajout de produit via image/texte (comportement existant
conservé pour compatibilité).
"""
import re
import datetime

from app.core import database
from app.services import handover_service
from app.services.sheets_service import SheetsService
from app.services.whatsapp_service import WhatsAppService


HELP_TEXT = (
    "🤖 *Commandes disponibles*\n\n"
    "/commandes — commandes du jour\n"
    "/stats — statistiques rapides\n"
    "/stock <produit> <qté> — modifier le stock\n"
    "/prix <produit> <prix> — modifier un prix\n"
    "/ajouter <nom>|<description>|<prix>|<stock> — ajouter un produit\n"
    "/human <numéro> — prendre la main sur une conversation\n"
    "/reprendre <numéro> — rendre la main à l'IA\n"
    "/close <numéro> — clôturer et rendre la main à l'IA\n"
    "/mode <numéro> <bot|human> — changer le mode d'une conversation\n"
    "/envoyer <numéro> <message> — répondre à un client manuellement\n"
    "/stop <numéro|all> — désactiver le bot (conversation ou boutique)\n"
    "/start <numéro> — réactiver le bot pour une conversation\n"
    "/help — afficher cette aide"
)


def _parse_vendor_caption(caption):
    """Extrait dynamiquement les champs depuis le texte/légende envoyé par
    le vendeur au format 'Nom: X | Description: Y | Prix: Z | Stock: W'."""
    data = {"nom": "", "description": "", "prix": 0, "stock": 0}
    if not caption:
        return data

    parts = caption.split("|")
    for part in parts:
        if ":" in part:
            key, val = part.split(":", 1)
            key = key.strip().lower()
            val = val.strip()

            if key in ["nom", "article", "produit"]:
                data["nom"] = val
            elif key in ["description", "desc"]:
                data["description"] = val
            elif key in ["prix", "price"]:
                try:
                    data["prix"] = float(re.sub(r"[^\d.]", "", val))
                except ValueError:
                    data["prix"] = 0
            elif key in ["stock", "quantite", "quantité"]:
                try:
                    data["stock"] = int(re.sub(r"\D", "", val))
                except ValueError:
                    data["stock"] = 0
    return data


def _reply(phone_number_id, vendor_phone, text, access_token):
    WhatsAppService.send_message(
        phone_number_id=phone_number_id,
        recipient_phone=vendor_phone,
        message_text=text,
        access_token=access_token,
    )


def _handle_help(phone_number_id, vendor_phone, access_token):
    _reply(phone_number_id, vendor_phone, HELP_TEXT, access_token)


def _handle_stock(phone_number_id, vendor_phone, args, tenant, access_token):
    # Format attendu : /stock <nom produit> <quantité>
    match = re.match(r"^(.*)\s+(-?\d+)$", args.strip())
    if not match:
        _reply(phone_number_id, vendor_phone,
               "⚠️ Format : /stock <produit> <quantité>\nEx: /stock T-Shirt Noir 20",
               access_token)
        return

    product_name, qty_str = match.group(1).strip(), match.group(2)
    sheets_id = tenant.get("sheets_id")
    catalog = SheetsService.fetch_catalog(sheets_id)

    existing = next(
        (p for p in catalog if p.get("nom", "").strip().lower() == product_name.lower()),
        None,
    )
    if not existing:
        _reply(phone_number_id, vendor_phone,
               f"❌ Produit '{product_name}' introuvable dans le catalogue.",
               access_token)
        return

    success = SheetsService.add_or_update_product(
        sheets_id=sheets_id,
        product_name=existing.get("nom"),
        description=existing.get("description", ""),
        price=existing.get("prix", 0),
        stock=int(qty_str),
        image_url=existing.get("image_url", ""),
    )
    if success:
        _reply(phone_number_id, vendor_phone,
               f"✅ Stock mis à jour : {existing.get('nom')} → {qty_str} unités.",
               access_token)
    else:
        _reply(phone_number_id, vendor_phone, "❌ Erreur lors de la mise à jour du stock.", access_token)


def _handle_prix(phone_number_id, vendor_phone, args, tenant, access_token):
    # Format attendu : /prix <nom produit> <nouveau prix>
    match = re.match(r"^(.*)\s+(\d+(?:\.\d+)?)$", args.strip())
    if not match:
        _reply(phone_number_id, vendor_phone,
               "⚠️ Format : /prix <produit> <nouveau prix>\nEx: /prix T-Shirt Noir 180",
               access_token)
        return

    product_name, price_str = match.group(1).strip(), match.group(2)
    sheets_id = tenant.get("sheets_id")
    catalog = SheetsService.fetch_catalog(sheets_id)

    existing = next(
        (p for p in catalog if p.get("nom", "").strip().lower() == product_name.lower()),
        None,
    )
    if not existing:
        _reply(phone_number_id, vendor_phone,
               f"❌ Produit '{product_name}' introuvable dans le catalogue.",
               access_token)
        return

    success = SheetsService.add_or_update_product(
        sheets_id=sheets_id,
        product_name=existing.get("nom"),
        description=existing.get("description", ""),
        price=float(price_str),
        stock=existing.get("stock", 0),
        image_url=existing.get("image_url", ""),
    )
    if success:
        _reply(phone_number_id, vendor_phone,
               f"💰 Prix mis à jour : {existing.get('nom')} → {price_str} DH.",
               access_token)
    else:
        _reply(phone_number_id, vendor_phone, "❌ Erreur lors de la mise à jour du prix.", access_token)


def _handle_ajouter(phone_number_id, vendor_phone, args, tenant, access_token):
    # Format attendu : /ajouter Nom|Description|Prix|Stock
    parts = [p.strip() for p in args.split("|")]
    if len(parts) < 4:
        _reply(phone_number_id, vendor_phone,
               "⚠️ Format : /ajouter Nom|Description|Prix|Stock\n"
               "Ex: /ajouter T-Shirt Rouge|Coton 100%|150|20",
               access_token)
        return

    nom, description, prix_str, stock_str = parts[0], parts[1], parts[2], parts[3]
    try:
        prix = float(re.sub(r"[^\d.]", "", prix_str))
        stock = int(re.sub(r"\D", "", stock_str))
    except ValueError:
        _reply(phone_number_id, vendor_phone, "❌ Prix ou stock invalide.", access_token)
        return

    success = SheetsService.add_or_update_product(
        sheets_id=tenant.get("sheets_id"),
        product_name=nom,
        description=description,
        price=prix,
        stock=stock,
        image_url="",
    )
    if success:
        _reply(phone_number_id, vendor_phone, f"✅ Produit '{nom}' enregistré avec succès !", access_token)
    else:
        _reply(phone_number_id, vendor_phone, "❌ Erreur lors de l'ajout du produit.", access_token)


def _handle_commandes(phone_number_id, vendor_phone, tenant, access_token):
    sheets_id = tenant.get("sheets_id")
    try:
        client = SheetsService.get_gspread_client()
        if not client:
            _reply(phone_number_id, vendor_phone, "❌ Connexion Google Sheets indisponible.", access_token)
            return
        spreadsheet = client.open_by_key(sheets_id)
        sheet = spreadsheet.worksheet("Commandes")
        records = sheet.get_all_records()
    except Exception as e:
        _reply(phone_number_id, vendor_phone, f"❌ Erreur lors de la lecture des commandes : {e}", access_token)
        return

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_orders = [r for r in records if str(r.get("Date", "")).startswith(today_str)]

    if not today_orders:
        _reply(phone_number_id, vendor_phone, "📦 Aucune commande aujourd'hui.", access_token)
        return

    lines = [f"📦 *{len(today_orders)} commande(s) aujourd'hui*\n"]
    for o in today_orders[-10:]:
        lines.append(f"• {o.get('Nom Client', '?')} — {o.get('Total (DH)', '?')} ({o.get('Statut', '?')})")
    _reply(phone_number_id, vendor_phone, "\n".join(lines), access_token)


def _handle_stats(phone_number_id, vendor_phone, tenant, access_token):
    sheets_id = tenant.get("sheets_id")
    try:
        client = SheetsService.get_gspread_client()
        if not client:
            _reply(phone_number_id, vendor_phone, "❌ Connexion Google Sheets indisponible.", access_token)
            return
        spreadsheet = client.open_by_key(sheets_id)
        sheet = spreadsheet.worksheet("Commandes")
        records = sheet.get_all_records()
    except Exception as e:
        _reply(phone_number_id, vendor_phone, f"❌ Erreur lors de la lecture des statistiques : {e}", access_token)
        return

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_orders = [r for r in records if str(r.get("Date", "")).startswith(today_str)]

    def parse_total(row):
        try:
            return float(re.sub(r"[^\d.]", "", str(row.get("Total (DH)", "0"))))
        except ValueError:
            return 0.0

    total_today = sum(parse_total(o) for o in today_orders)
    total_all = sum(parse_total(o) for o in records)

    text = (
        f"📊 *Statistiques*\n\n"
        f"Aujourd'hui : {len(today_orders)} commande(s), {total_today:.0f} DH\n"
        f"Depuis le début : {len(records)} commande(s), {total_all:.0f} DH"
    )
    _reply(phone_number_id, vendor_phone, text, access_token)


def _handle_mode(phone_number_id, vendor_phone, args, access_token):
    parts = args.strip().split()
    if len(parts) != 2 or parts[1] not in ("bot", "human"):
        _reply(phone_number_id, vendor_phone,
               "⚠️ Format : /mode <numéro client> <bot|human>",
               access_token)
        return

    customer_phone, mode = parts[0], parts[1]
    success = database.set_conversation_mode(phone_number_id, customer_phone, mode)
    if success:
        _reply(phone_number_id, vendor_phone, f"✅ Mode de {customer_phone} → {mode.upper()}.", access_token)
    else:
        _reply(phone_number_id, vendor_phone, "❌ Erreur lors du changement de mode.", access_token)


def _handle_human(phone_number_id, vendor_phone, args, tenant, access_token):
    """/human <numéro> — le vendeur prend la main volontairement, sans que
    le client ait rien demandé (doc Phase 2, section 9)."""
    customer_phone = args.strip()
    if not customer_phone:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /human <numéro client>", access_token)
        return

    handover_service.activate_human_mode(
        phone_number_id, customer_phone, tenant, access_token,
        trigger_message="(pris en charge manuellement par le vendeur)",
    )
    _reply(phone_number_id, vendor_phone,
           f"🙋 Vous gérez maintenant la conversation avec {customer_phone}.\n"
           f"Répondez avec : /envoyer {customer_phone} <message>",
           access_token)


def _handle_reprendre(phone_number_id, vendor_phone, args, access_token):
    """/reprendre <numéro> — rend la main à l'IA (doc Phase 2, section 8)."""
    customer_phone = args.strip()
    if not customer_phone:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /reprendre <numéro client>", access_token)
        return

    handover_service.deactivate_human_mode(phone_number_id, customer_phone)
    _reply(phone_number_id, vendor_phone, f"🤖 L'IA reprend la conversation avec {customer_phone}.", access_token)


def _handle_close(phone_number_id, vendor_phone, args, access_token):
    """/close <numéro> — clôture la conversation. V1 : équivalent à /reprendre,
    avec historique conservé (doc Phase 2, section 10)."""
    customer_phone = args.strip()
    if not customer_phone:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /close <numéro client>", access_token)
        return

    handover_service.deactivate_human_mode(phone_number_id, customer_phone)
    _reply(phone_number_id, vendor_phone, f"✅ Conversation avec {customer_phone} clôturée (mode IA restauré).", access_token)


def _handle_stop(phone_number_id, vendor_phone, args, access_token):
    target = args.strip()
    if not target:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /stop <numéro> ou /stop all", access_token)
        return

    if target.lower() == "all":
        # Portée volontairement limitée : on ne fait PAS un arrêt global automatique
        # sans confirmation explicite, pour éviter un incident si le vendeur se trompe.
        _reply(phone_number_id, vendor_phone,
               "⚠️ Pour désactiver TOUT le bot, confirmez avec : /stop all confirmer",
               access_token)
        return

    if target.lower().startswith("all confirmer"):
        # Non implémenté : nécessiterait un flag au niveau tenant. Laissé en TODO explicite.
        _reply(phone_number_id, vendor_phone,
               "⚠️ Arrêt global pas encore disponible — utilisez /human <numéro> conversation par conversation.",
               access_token)
        return

    database.set_conversation_mode(phone_number_id, target, "human")
    _reply(phone_number_id, vendor_phone, f"🛑 Bot désactivé pour {target} (mode humain).", access_token)


def _handle_start(phone_number_id, vendor_phone, args, access_token):
    target = args.strip()
    if not target:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /start <numéro>", access_token)
        return
    database.set_conversation_mode(phone_number_id, target, "bot")
    _reply(phone_number_id, vendor_phone, f"▶️ Bot réactivé pour {target}.", access_token)


def _handle_envoyer(phone_number_id, vendor_phone, args, access_token):
    match = re.match(r"^(\S+)\s+(.+)$", args.strip(), re.DOTALL)
    if not match:
        _reply(phone_number_id, vendor_phone, "⚠️ Format : /envoyer <numéro> <message>", access_token)
        return

    customer_phone, message_text = match.group(1), match.group(2)
    success = WhatsAppService.send_message(
        phone_number_id=phone_number_id,
        recipient_phone=customer_phone,
        message_text=message_text,
        access_token=access_token,
    )
    database.save_message(phone_number_id, customer_phone, "assistant", message_text)

    if success:
        _reply(phone_number_id, vendor_phone, f"📤 Message envoyé à {customer_phone}.", access_token)
    else:
        _reply(phone_number_id, vendor_phone, f"❌ Échec de l'envoi à {customer_phone}.", access_token)


def handle_vendor_message(phone_number_id, vendor_phone, msg_type, message_data, tenant, access_token):
    """Point d'entrée unique pour tout message provenant du vendeur.

    Règle d'or : ce message ne doit jamais être transmis au traitement client.
    """
    # --- Cas image avec légende produit (comportement existant conservé) ---
    if msg_type == "image":
        from app.services.storage_service import StorageService

        media_id = message_data.get("image", {}).get("id")
        caption = message_data.get("image", {}).get("caption", "")
        parsed = _parse_vendor_caption(caption)
        product_name = parsed.get("nom")

        if not product_name:
            _reply(phone_number_id, vendor_phone,
                   "⚠️ *Format d'image incorrect.*\nLégende attendue :\n"
                   "`Nom: [Nom] | Description: [Texte] | Prix: [150] | Stock: [10]`",
                   access_token)
            return

        store_id = tenant.get("store_id", "default_store")
        image_url = StorageService.upload_whatsapp_media(
            media_id=media_id, access_token=access_token,
            store_id=store_id, product_name=product_name,
        )
        if image_url:
            success = SheetsService.add_or_update_product(
                sheets_id=tenant.get("sheets_id"),
                product_name=product_name,
                description=parsed.get("description", ""),
                price=parsed.get("prix", 0),
                stock=parsed.get("stock", 0),
                image_url=image_url,
            )
            msg = (f"✅ *Produit avec photo '{product_name}' enregistré !*" if success
                   else "❌ Erreur d'enregistrement Google Sheets.")
            _reply(phone_number_id, vendor_phone, msg, access_token)
        return

    if msg_type != "text":
        return  # Type de message non géré côté vendeur (audio, sticker...) → silence

    text_body = message_data.get("text", {}).get("body", "").strip()

    # --- Ancien format "Nom: X | Description: Y..." conservé pour compatibilité ---
    if not text_body.startswith("/") and ("nom:" in text_body.lower() or "article:" in text_body.lower()):
        parsed = _parse_vendor_caption(text_body)
        if parsed.get("nom") and parsed.get("description"):
            success = SheetsService.add_or_update_product(
                sheets_id=tenant.get("sheets_id"),
                product_name=parsed["nom"], description=parsed["description"],
                price=parsed.get("prix", 0), stock=parsed.get("stock", 0), image_url="",
            )
            msg = (f"✅ *Produit '{parsed['nom']}' enregistré avec succès !*" if success
                   else "❌ Erreur d'enregistrement.")
            _reply(phone_number_id, vendor_phone, msg, access_token)
        else:
            _reply(phone_number_id, vendor_phone,
                   "⚠️ *Format texte incomplet.*\n`Nom: [Nom] | Description: [Texte] | Prix: [150] | Stock: [20]`",
                   access_token)
        return

    # --- Commandes slash ---
    if text_body.startswith("/"):
        command, _, args = text_body[1:].partition(" ")
        command = command.lower()

        if command == "help":
            _handle_help(phone_number_id, vendor_phone, access_token)
        elif command == "stock":
            _handle_stock(phone_number_id, vendor_phone, args, tenant, access_token)
        elif command == "prix":
            _handle_prix(phone_number_id, vendor_phone, args, tenant, access_token)
        elif command == "ajouter":
            _handle_ajouter(phone_number_id, vendor_phone, args, tenant, access_token)
        elif command == "commandes":
            _handle_commandes(phone_number_id, vendor_phone, tenant, access_token)
        elif command == "stats":
            _handle_stats(phone_number_id, vendor_phone, tenant, access_token)
        elif command == "human":
            _handle_human(phone_number_id, vendor_phone, args, tenant, access_token)
        elif command == "reprendre":
            _handle_reprendre(phone_number_id, vendor_phone, args, access_token)
        elif command == "close":
            _handle_close(phone_number_id, vendor_phone, args, access_token)
        elif command == "mode":
            _handle_mode(phone_number_id, vendor_phone, args, access_token)
        elif command == "stop":
            _handle_stop(phone_number_id, vendor_phone, args, access_token)
        elif command == "start":
            _handle_start(phone_number_id, vendor_phone, args, access_token)
        elif command == "envoyer":
            _handle_envoyer(phone_number_id, vendor_phone, args, access_token)
        else:
            _reply(phone_number_id, vendor_phone,
                   f"❓ Commande inconnue : /{command}\nTapez /help pour la liste.",
                   access_token)
        return

    # --- Message normal du vendeur (ex: "Bonjour") ---
    # Règle d'or du doc : silence total, sauf s'il n'y a qu'UNE seule conversation
    # active en HUMAN_MODE pour cette boutique — dans ce cas, on relaie par confort,
    # car l'intention est sans ambiguïté.
    human_conversations = database.get_human_mode_conversations(phone_number_id)
    if len(human_conversations) == 1:
        customer_phone = human_conversations[0]
        WhatsAppService.send_message(
            phone_number_id=phone_number_id,
            recipient_phone=customer_phone,
            message_text=text_body,
            access_token=access_token,
        )
        database.save_message(phone_number_id, customer_phone, "assistant", text_body)
    # Sinon (0 ou plusieurs conversations en mode humain) : silence total, comme demandé.
    return