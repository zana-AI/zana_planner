"""Import a French news PDF into Xaana's Library and Actualités deck.

Run inside zana-webapp. The importer is idempotent: content is keyed by its
canonical URL, the stored PDF by checksum, and notes by their normalised front.
Existing notes keep their scheduling and receive this source as extra context.
"""
from __future__ import annotations

import argparse
import hashlib
import urllib.request

SOURCE_URL = "https://maisons-alfort.fr/wp-content/uploads/2018/12/web-maisons-alfort-le-mag-septembre-2026.pdf"
TITLE = "Maisons-Alfort le mag - septembre 2026"
USER_ID = "108648163"
DECK_PATH = "French::Actualités"

# Front is the recall target. Back is Persian only; examples keep the French
# expression in a natural context and are shown only after reveal.
CARDS = [
    ("tenir à + infinitif", "مایل/مصر بودن به انجام کاری؛ برای بیان یک قصد یا تأکید مهم، رسمی‌تر از vouloir.", "Je tiens à vous remercier pour votre aide."),
    ("caniculaire", "بسیار گرم؛ مربوط به موج گرمای شدید تابستانی.", "Après une semaine caniculaire, la ville a ouvert des lieux frais."),
    ("éprouvant, éprouvante", "فرساینده و سخت از نظر جسمی یا روحی.", "La journée a été éprouvante pour les équipes de secours."),
    ("avoir dû être + participe passé", "ساختاری برای گفتن اینکه کاری ناچاراً انجام شده یا تغییری اجباری رخ داده است.", "Les horaires ont dû être modifiés à cause de la chaleur."),
    ("pas moins de", "حداقل؛ تأکید می‌کند که مقدار اعلام‌شده چشمگیر است.", "Pas moins de cinquante personnes ont participé à la réunion."),
    ("engager des fonds", "بودجه یا پولی را برای یک هدف مشخص اختصاص دادن.", "La commune a engagé des fonds pour rénover l'école."),
    ("le cadre de vie", "محیط و شرایط روزمره‌ای که فرد در آن زندگی می‌کند.", "Les habitants veulent préserver leur cadre de vie."),
    ("néanmoins", "با این حال؛ برای نشان دادن مخالفت یا محدودیت نسبت به جملهٔ قبل.", "Le projet est coûteux ; néanmoins, il reste nécessaire."),
    ("être fermement opposé à", "قاطعانه با یک تصمیم، طرح یا نظر مخالفت داشتن.", "Les riverains sont fermement opposés à cette construction."),
    ("funeste", "شوم و دارای پیامدهای بسیار زیان‌بار؛ واژه‌ای قوی و رسمی.", "Il redoute les conséquences funestes de cette décision."),
    ("l'ampleur", "وسعت، بزرگی یا دامنهٔ واقعی یک پدیده یا مسئله.", "Nous n'avions pas mesuré l'ampleur des dégâts."),
    ("être cerné par", "از چند جهت با چیزی احاطه یا محصور بودن.", "Le quartier est cerné par des routes très fréquentées."),
    ("tant ... que ...", "هم ... و هم ...؛ دو جنبه را با هم بیان می‌کند.", "La mesure est utile tant pour les familles que pour les commerçants."),
    ("être intransigeant, intransigeante", "در یک موضوع کوتاه نیامدن و سازش نپذیرفتن.", "Elle se montre intransigeante sur la sécurité."),
    ("en la matière", "در این زمینه یا در این خصوص؛ عبارت رسمی.", "En la matière, la mairie suivra les recommandations."),
    ("une concertation préalable", "مشورت رسمی با مردم و ذی‌نفعان پیش از نهایی‌شدن یک طرح.", "Une concertation préalable aura lieu avant les travaux."),
    ("mener à bien", "کاری یا پروژه‌ای را با موفقیت تا پایان رساندن.", "Ils ont mené à bien la rénovation malgré les retards."),
    ("se devoir de + infinitif", "خود را موظف دانستن که کاری انجام دهد؛ رسمی‌تر از devoir.", "Les responsables se doivent de répondre aux habitants."),
    ("considérer comme", "چیزی را دارای یک ویژگی یا وضعیت مشخص دانستن.", "Je considère cette solution comme insuffisante."),
    ("solennellement", "به شکلی رسمی، جدی و با اهمیت ویژه.", "Le maire a solennellement appelé au calme."),
    ("faire obstacle à", "مانع رخ دادن یا پیش رفتن چیزی شدن.", "Cette règle peut faire obstacle au projet."),
    ("mortifère", "مرگ‌آور یا به‌شدت زیان‌بار؛ غالباً در نقد سیاسی یا اجتماعی.", "Ils dénoncent une politique mortifère pour le service public."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--user-id", default=USER_ID)
    args = parser.parse_args()
    if not args.publish:
        print(f"Would add {len(CARDS)} cards to {DECK_PATH} from {SOURCE_URL}")
        return

    from repositories.content_repo import ContentRepository
    from services.object_storage_service import ObjectStorageService
    from services import flashcard_service

    payload = urllib.request.urlopen(SOURCE_URL, timeout=60).read()
    checksum = hashlib.sha256(payload).hexdigest()
    content_repo = ContentRepository()
    content_id = content_repo.upsert_content(
        canonical_url=SOURCE_URL, original_url=SOURCE_URL, provider="telegram_pdf",
        content_type="text", title=TITLE, author_channel="Ville de Maisons-Alfort",
        language="fr", published_at="2026-09-01",
        metadata_json={"mime_type": "application/pdf", "source_url": SOURCE_URL, "issue": "septembre 2026"},
    )
    content_repo.claim_content_owner(content_id, args.user_id)
    content_repo.add_user_content(args.user_id, content_id)
    asset = content_repo.get_latest_content_asset(content_id, "pdf_source")
    if not asset or asset.get("checksum") != checksum:
        storage = ObjectStorageService()
        uri, size = storage.upload_pdf_bytes(f"pdf/{args.user_id}/{content_id}/{checksum}.pdf", payload)
        asset_id = content_repo.add_content_asset(content_id, "pdf_source", uri, size, checksum)
    else:
        asset_id = str(asset["id"])

    reference = {"kind": "asset", "content_id": content_id, "asset_id": asset_id,
                 "locator": {"page": 3, "section": "Édito"}, "label": TITLE}
    created = 0
    for front, back, example in CARDS:
        note = flashcard_service.save_context_note(
            args.user_id, DECK_PATH,
            {"front": front, "back": back, "example": example, "source_page": "3", "source_collection": "Actualités"},
            references=[reference],
            source="actualites",
        )
        created += int(bool(note.get("_created")))
    print(f"Library content={content_id} asset={asset_id}; processed={len(CARDS)} new={created}")


if __name__ == "__main__":
    main()
