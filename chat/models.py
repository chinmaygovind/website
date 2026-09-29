"""Chat's tables. All new, all prefixed ``chat_``, all made by ``create_all``.

The shared ``users`` table is read, never mapped: chat needs a user's id, name
and picture and nothing else, so it asks with raw SQL in ``people.py`` rather
than carrying a sixth copy of ``User`` for three columns.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Conversation(db.Model):
    """A thread. A DM is a conversation with two members and a ``dm_key``."""
    __tablename__ = "chat_conversations"

    id = db.Column(db.Integer, primary_key=True)
    is_group = db.Column(db.Boolean, default=False, nullable=False)
    name = db.Column(db.String(60), nullable=True)
    # "<low id>:<high id>" for a DM, NULL for a group. Unique, so two people
    # opening a chat with each other at the same moment get the one thread.
    dm_key = db.Column(db.String(24), unique=True, nullable=True)
    created_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Member(db.Model):
    __tablename__ = "chat_members"

    conversation_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id"),
                                primary_key=True)
    user_id = db.Column(db.Integer, primary_key=True, index=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    # The id of the newest message this member has seen. Unread counts and
    # read receipts are both this one number.
    last_read_id = db.Column(db.Integer, default=0, nullable=False)


class Message(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id"),
                                nullable=False, index=True)
    sender_id = db.Column(db.Integer, nullable=False)
    kind = db.Column(db.String(10), default="text", nullable=False)  # text | invite | system
    body = db.Column(db.Text, nullable=False, default="")
    # For an invite: the game and the room code. Never a URL - the link is
    # built from these on the way out, so a message cannot point anywhere else.
    game = db.Column(db.String(10), nullable=True)
    room = db.Column(db.String(8), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Follow(db.Model):
    """One-way: ``user_id`` added ``target_id``. No acceptance step."""
    __tablename__ = "chat_follows"

    user_id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, primary_key=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Block(db.Model):
    __tablename__ = "chat_blocks"

    user_id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, primary_key=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    __tablename__ = "chat_reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("chat_messages.id"), nullable=False)
    reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Prefs(db.Model):
    __tablename__ = "chat_prefs"

    user_id = db.Column(db.Integer, primary_key=True)
    # "anyone" or "following": who may start a conversation with this person.
    dm_policy = db.Column(db.String(10), default="anyone", nullable=False)
