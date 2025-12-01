from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-in-prod"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///assessments.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------- LOGIN CONFIG ---------------------- #

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------- MODELS ---------------------- #

class Template(db.Model):
    __tablename__ = "templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    template_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    questions = db.relationship("Question", backref="template", cascade="all, delete-orphan")


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("templates.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    help_text = db.Column(db.Text, nullable=True)
    required = db.Column(db.Boolean, default=True)
    question_type = db.Column(db.String(50), default="text")
    options_json = db.Column(db.Text, nullable=True)


class Assessment(db.Model):
    __tablename__ = "assessments"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("templates.id"), nullable=False)
    template = db.relationship("Template")
    name = db.Column(db.String(200), nullable=False)
    vendor_name = db.Column(db.String(200), nullable=True)
    product_name = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.relationship("Answer", backref="assessment", cascade="all, delete-orphan")


class Answer(db.Model):
    __tablename__ = "answers"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    question = db.relationship("Question")
    answer_text = db.Column(db.Text, nullable=True)


# ---------------------- SEED DEFAULT TEMPLATES ---------------------- #

def seed_default_templates():
    if Template.query.count() > 0:
        return

    due_diligence = Template(
        name="Third-Party Due Diligence Assessment",
        template_type="Due Diligence",
        description="Basic vendor due diligence questionnaire."
    )
    db.session.add(due_diligence)
    db.session.flush()

    dd_questions = [
        "What is the legal name of the vendor?",
        "Describe the services the vendor will provide.",
        "Will the vendor process personal data?",
        "Will the vendor process special categories of personal data?",
        "Where will the data be stored and processed?",
        "Does the vendor have security certifications?",
    ]
    for q in dd_questions:
        db.session.add(Question(template_id=due_diligence.id, text=q, question_type="textarea"))

    dpia = Template(
        name="Data Protection Impact Assessment (DPIA)",
        template_type="DPIA",
        description="High-level DPIA for internal products."
    )
    db.session.add(dpia)
    db.session.flush()

    dpia_questions = [
        "Describe the processing activity.",
        "What types of personal data are processed?",
        "Who are the data subjects?",
        "What risks exist?",
        "What safeguards are implemented?",
        "Any data transfer outside the EEA?",
    ]
    for q in dpia_questions:
        db.session.add(Question(template_id=dpia.id, text=q, question_type="textarea"))

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_default_templates()


# ---------------------- AUTH ROUTES ---------------------- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return redirect(url_for("register"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("User created successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("main"))

        flash("Invalid username or password", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------- MAIN PAGE ---------------------- #

@app.route("/main")
@login_required
def main():
    templates_count = Template.query.count()
    assessments_count = Assessment.query.count()
    return render_template("index.html",
                           templates_count=templates_count,
                           assessments_count=assessments_count)


# ---------------------- PROTECTED ROUTES ---------------------- #

@app.route("/")
@login_required
def index():
    return redirect(url_for("main"))


@app.route("/templates")
@login_required
def templates_list():
    templates = Template.query.order_by(Template.id.desc()).all()
    return render_template("templates_list.html", templates=templates)


@app.route("/templates/new", methods=["GET", "POST"])
@login_required
def template_new():
    if request.method == "POST":
        name = request.form.get("name")
        template_type = request.form.get("template_type")
        description = request.form.get("description")
        if not name or not template_type:
            flash("Name and type are required.", "danger")
            return redirect(url_for("template_new"))

        t = Template(name=name, template_type=template_type, description=description)
        db.session.add(t)
        db.session.commit()
        flash("Template created.", "success")
        return redirect(url_for("template_edit", template_id=t.id))

    return render_template("template_edit.html", template=None)


@app.route("/templates/<int:template_id>", methods=["GET", "POST"])
@login_required
def template_edit(template_id):
    template = Template.query.get_or_404(template_id)

    if request.method == "POST":
        q_text = request.form.get("question_text")
        q_help = request.form.get("help_text")
        q_type = request.form.get("question_type", "text")

        if q_text:
            q = Question(template_id=template.id, text=q_text, help_text=q_help, question_type=q_type)
            db.session.add(q)
            db.session.commit()
            flash("Question added.", "success")

        return redirect(url_for("template_edit", template_id=template.id))

    questions = Question.query.filter_by(template_id=template.id).all()
    return render_template("template_edit.html", template=template, questions=questions)


@app.route("/templates/<int:template_id>/questions/<int:question_id>/delete", methods=["POST"])
@login_required
def question_delete(template_id, question_id):
    q = Question.query.get_or_404(question_id)
    db.session.delete(q)
    db.session.commit()
    flash("Question deleted.", "info")
    return redirect(url_for("template_edit", template_id=template_id))


@app.route("/templates/<int:template_id>/questions/<int:question_id>/edit", methods=["GET", "POST"])
@login_required
def question_edit(template_id, question_id):
    template = Template.query.get_or_404(template_id)
    question = Question.query.get_or_404(question_id)

    if request.method == "POST":
        question.text = request.form.get("text")
        question.help_text = request.form.get("help_text")
        question.question_type = request.form.get("question_type")
        db.session.commit()
        flash("Question updated.", "success")
        return redirect(url_for("template_edit", template_id=template_id))

    return render_template("question_edit.html", template=template, question=question)


@app.route("/assessments")
@login_required
def assessments_list():
    assessments = Assessment.query.order_by(Assessment.created_at.desc()).all()
    return render_template("assessments_list.html", assessments=assessments)


@app.route("/assessments/new/<int:template_id>", methods=["GET", "POST"])
@login_required
def assessment_new(template_id):
    template = Template.query.get_or_404(template_id)
    questions = Question.query.filter_by(template_id=template.id).all()

    if request.method == "POST":
        name = request.form.get("assessment_name")
        vendor_name = request.form.get("vendor_name")
        product_name = request.form.get("product_name")

        if not name:
            flash("Assessment name is required.", "danger")
            return redirect(url_for("assessment_new", template_id=template.id))

        assessment = Assessment(
            template_id=template.id,
            name=name,
            vendor_name=vendor_name,
            product_name=product_name
        )
        db.session.add(assessment)
        db.session.flush()

        for q in questions:
            field_name = f"question_{q.id}"
            ans_text = request.form.get(field_name)
            answer = Answer(
                assessment_id=assessment.id,
                question_id=q.id,
                answer_text=ans_text
            )
            db.session.add(answer)

        db.session.commit()
        flash("Assessment saved.", "success")
        return redirect(url_for("assessment_view", assessment_id=assessment.id))

    return render_template("assessment_new.html", template=template, questions=questions)


@app.route("/assessments/<int:assessment_id>")
@login_required
def assessment_view(assessment_id):
    assessment = Assessment.query.get_or_404(assessment_id)
    answers_by_question = {ans.question_id: ans for ans in assessment.answers}
    return render_template("assessment_view.html",
                           assessment=assessment,
                           answers_by_question=answers_by_question)


if __name__ == "__main__":
    app.run(debug=True)
