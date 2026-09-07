#!/usr/bin/env python3
"""Apply a curated quality pass to the personal Edito B1 cards.

Dry-run by default; --apply publishes through flashcard_service so source_key
and FSRS-linked note identity remain safe.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app/tm_bot")

from sqlalchemy import text

from db.postgres_db import get_db_session
from services import flashcard_service

USER_ID = "108648163"

EDIT = {
    "gêner": {
        "front": "gêner",
        "back": "Mettre quelqu’un mal à l’aise ou causer un désagrément.",
        "example": "Ça me gêne de parler devant tout le monde.",
    },
    "plaire à": {
        "front": "plaire à quelqu’un",
        "back": "Être agréable ou susciter l’appréciation de quelqu’un.",
        "example": "Ce livre plaît beaucoup aux étudiants.",
    },
    "se tromper": {
        "front": "se tromper",
        "back": "Commettre une erreur ou avoir une opinion incorrecte.",
        "example": "Je me suis trompé de chemin.",
    },
    "être / suivre : suis": {
        "front": "être / suivre : je suis",
        "back": "« Je suis » est la première personne du singulier au présent de être et de suivre.",
        "example": "Je suis fatigué. / Je suis le guide.",
    },
    "citoyen / citoyenne": {
        "front": "citoyen / citoyenne",
        "back": "Personne qui appartient à une nation et bénéficie de droits et assume des devoirs civiques.",
        "example": "Chaque citoyen peut participer à la vie démocratique.",
    },
    "jalouse": {
        "front": "jaloux / jalouse",
        "back": "Qui éprouve de la jalousie ou craint de perdre l’affection de quelqu’un.",
        "example": "Il est jaloux de son frère. Elle est jalouse de sa sœur.",
    },
    "À quelle vitesse": {
        "front": "à quelle vitesse",
        "back": "À quel rythme ; avec quelle rapidité.",
        "example": "À quelle vitesse roule ce train ?",
    },
    "avertir d'un retard": {
        "front": "avertir quelqu’un de quelque chose",
        "back": "Informer quelqu’un d’un fait ou d’un problème à venir.",
        "example": "Je dois l’avertir de mon retard.",
    },
    "ça m'énerve": {
        "front": "énerver quelqu’un",
        "back": "Agacer ou irriter quelqu’un.",
        "example": "Le bruit des travaux m’énerve.",
    },
    "cela me fait chier": {
        "front": "faire chier quelqu’un",
        "back": "Ennuyer ou agacer fortement quelqu’un. Expression vulgaire et familière.",
        "example": "Arrête de me faire chier !",
    },
    "la façon": {
        "front": "la façon dont",
        "back": "La manière dont quelque chose se fait.",
        "example": "J’aime la façon dont elle explique les choses.",
    },
    "reprocher (qqch à qqn)": {
        "front": "reprocher quelque chose à quelqu’un",
        "back": "Exprimer à quelqu’un son mécontentement à propos de quelque chose.",
        "example": "Je ne lui reproche pas son erreur.",
    },
    "s'approcher (de)": {
        "front": "s’approcher de",
        "back": "Venir plus près de quelqu’un ou de quelque chose.",
        "example": "Le chien s’est approché de la porte.",
    },
    "l'époque où": {
        "front": "à l’époque où",
        "back": "À la période où ; pendant le temps où.",
        "example": "À l’époque où je vivais à Paris, je prenais le métro chaque jour.",
    },
    "la hâte": {
        "front": "avoir hâte de",
        "back": "Être impatient de faire quelque chose.",
        "example": "J’ai hâte de commencer mes vacances.",
    },
    "maximum une par jour": {
        "front": "au maximum",
        "back": "Pas plus de ; tout au plus.",
        "example": "Vous pouvez prendre au maximum deux comprimés par jour.",
    },
    "père au foyer": {
        "front": "un père au foyer",
        "back": "Un père qui reste principalement à la maison pour s’occuper des enfants et du ménage.",
        "example": "Après la naissance de leur fille, il est devenu père au foyer.",
    },
    "remonter le moral (à qqn)": {
        "front": "remonter le moral à quelqu’un",
        "back": "Redonner courage et optimisme à quelqu’un.",
        "example": "Ses amis essaient de lui remonter le moral.",
    },
    "s'amouracher (de)": {
        "front": "s’amouracher de",
        "back": "Tomber amoureux de quelqu’un de façon soudaine et souvent passagère.",
        "example": "Il s’est amouraché d’une collègue de travail.",
    },
    "sans son autorisation": {
        "front": "sans autorisation",
        "back": "Sans avoir obtenu la permission ou l’accord nécessaire.",
        "example": "Il a utilisé la photo sans autorisation.",
    },
    "se remettre (de)": {
        "front": "se remettre de",
        "back": "Retrouver son équilibre ou sa santé après une difficulté.",
        "example": "Elle se remet lentement de cette épreuve.",
    },
    "un échec": {
        "front": "un échec",
        "back": "Le fait de ne pas réussir ; un résultat décevant.",
        "example": "Cet échec lui a permis de comprendre ses erreurs.",
    },
    "une avalanche de photos": {
        "front": "une avalanche de",
        "back": "Une très grande quantité de choses qui arrive en peu de temps, au sens figuré.",
        "example": "Après le concert, elle a reçu une avalanche de messages.",
    },
}
EDIT_BY_NEW_FRONT = {value["front"]: (old, value) for old, value in EDIT.items()}


def load() -> list[dict]:
    with get_db_session() as session:
        rows = session.execute(text("""
          WITH RECURSIVE tree AS (
            SELECT deck_id, name::text AS path FROM flashcard_deck
            WHERE user_id=:u AND parent_deck_id IS NULL
            UNION ALL
            SELECT d.deck_id, tree.path || '::' || d.name
            FROM flashcard_deck d JOIN tree ON d.parent_deck_id=tree.deck_id
            WHERE d.user_id=:u
          )
          SELECT n.note_id, n.deck_id, n.note_type, n.fields, t.path
          FROM flashcard_note n JOIN tree t ON t.deck_id=n.deck_id
          WHERE n.user_id=:u AND t.path LIKE 'French::Édito B1%%'
        """), {"u": USER_ID}).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            if isinstance(item["fields"], str):
                item["fields"] = json.loads(item["fields"])
            result.append(item)
        return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    notes = load()
    changes = []
    for note in notes:
        old = note["fields"].get("front", "")
        entry = EDIT.get(old) or EDIT_BY_NEW_FRONT.get(old, (None, None))[1]
        original = old if old in EDIT else EDIT_BY_NEW_FRONT.get(old, (None, None))[0]
        if entry is None:
            continue
        fields = dict(note["fields"])
        if original and original != entry["front"]:
            fields.setdefault("original_front", original)
        if fields.get("example") and fields["example"] != entry["example"]:
            fields["source_context"] = fields["example"]
        fields.update(entry)
        changes.append((note, fields))
    print(f"Édito B1 notes: {len(notes)}")
    print(f"Curated changes: {len(changes)}")
    for note, fields in changes:
        print(f"  {note['fields'].get('front')} -> {fields['front']}")
    if not args.apply:
        print("DRY RUN — no database changes")
        return 0
    for note, fields in changes:
        if flashcard_service.update_note(USER_ID, note["note_id"], fields) is None:
            raise RuntimeError(f"note disappeared: {note['note_id']}")
    print("APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
