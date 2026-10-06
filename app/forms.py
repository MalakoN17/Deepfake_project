from __future__ import annotations
"""Forms (Flask-WTF adds a CSRF token to every form automatically)."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length

PLATFORMS = [("Zoom", "Zoom"), ("Teams", "Microsoft Teams"), ("Webcam", "Webcam"), ("Other", "Other")]


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Sign in")


class UploadForm(FlaskForm):
    meeting_name = StringField("Meeting name", validators=[DataRequired(), Length(max=150)])
    platform = SelectField("Platform", choices=PLATFORMS)
    claimed_identity = SelectField("Participant claims to be", coerce=int)
    video = FileField("Video file", validators=[
        FileRequired(), FileAllowed(["mp4", "avi", "mov"], "Only MP4, AVI or MOV videos are allowed.")])
    submit = SubmitField("Analyze video")


class IdentityForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=100)])
    job_title = StringField("Job title", validators=[DataRequired(), Length(max=100)])
    photo = FileField("Reference photo", validators=[
        FileRequired(), FileAllowed(["jpg", "jpeg", "png"], "Only JPG or PNG images are allowed.")])
    submit = SubmitField("Add identity")
