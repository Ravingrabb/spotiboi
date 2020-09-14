from app import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_id = db.Column(db.String(80), unique=True, nullable=False)
    update = db.Column(db.Boolean,unique=False, nullable=False)
    history_id = db.Column(db.String(80), unique=True, nullable=True)
    update_time = db.Column(db.Integer, nullable=True)
    last_update = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return '<User %r>' % self.id