"""Provides all routes for the Social Insecurity application.

This file contains the routes for the application. It is imported by the social_insecurity package.
It also contains the SQL queries used for communicating with the database.
"""

from pathlib import Path

from flask import current_app as app
from flask import flash, redirect, render_template, send_from_directory, url_for

from social_insecurity import sqlite
from social_insecurity.forms import CommentsForm, FriendsForm, IndexForm, PostForm, ProfileForm

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import bleach

limiter = Limiter(
    get_remote_address,  # Bruker klientens IP-adresse for å begrense forespørsler
    app=app,
    default_limits=["200 per day", "50 per hour"]  # Globale standardgrenser
)



@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
@limiter.limit("5 per minute")  # Begrens til 5 forsøk per minutt
def index():
    """Provides the index page for the application.

    It reads the composite IndexForm and based on which form was submitted,
    it either logs the user in or registers a new user.

    If no form was submitted, it simply renders the index page.
    """
    index_form = IndexForm()
    login_form = index_form.login
    register_form = index_form.register

    if login_form.is_submitted() and login_form.submit.data:
        get_user = """
            SELECT *
            FROM Users
            WHERE username = ?;
            """
        user = sqlite.query(get_user, login_form.username.data, one=True)

        if user is None:
            flash("Sorry, this user does not exist!", category="warning")
        elif user["password"] != login_form.password.data:
            flash("Sorry, wrong password!", category="warning")
        elif user["password"] == login_form.password.data:
            return redirect(url_for("stream", username=login_form.username.data))

    elif register_form.validate_on_submit(): #validerer passord
        insert_user = """
            INSERT INTO Users (username, first_name, last_name, password)
            VALUES (?, ? ,? , ?);
            """
        sqlite.query(insert_user, register_form.username.data, register_form.first_name.data, register_form.last_name.data, register_form.password.data)
        flash("User successfully created!", category="success")
        return redirect(url_for("index"))

    return render_template("index.html.j2", title="Welcome", form=index_form)


@app.route("/stream/<string:username>", methods=["GET", "POST"])
def stream(username: str):
    """Provides the stream page for the application.

    If a form was submitted, it reads the form data and inserts a new post into the database.

    Otherwise, it reads the username from the URL and displays all posts from the user and their friends.
    """
    post_form = PostForm()
    get_user = """
        SELECT *
        FROM Users
        WHERE username = ?;
        """
    user = sqlite.query(get_user, username, one=True)

    if post_form.is_submitted():
        content = bleach.clean(post_form.content.data)
    
        filename = None  # Sett en standardverdi for filnavnet    


        if post_form.image.data:
            # Bruker filnavnet direkte uten sikring (ikke anbefalt)
            filename = post_form.image.data.filename
            path = Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"] / post_form.image.data.filename
            post_form.image.data.save(path)

        insert_post = """
            INSERT INTO Posts (u_id, content, image, creation_time)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_post, user["id"], content, filename)
        return redirect(url_for("stream", username=username))

    get_posts = """
         SELECT p.*, u.*, (SELECT COUNT(*) FROM Comments WHERE p_id = p.id) AS cc
         FROM Posts AS p JOIN Users AS u ON u.id = p.u_id
         WHERE p.u_id IN (SELECT u_id FROM Friends WHERE f_id = ?)
         OR p.u_id IN (SELECT f_id FROM Friends WHERE u_id = ?)
         OR p.u_id = ?
         ORDER BY p.creation_time DESC;
        """
    posts = sqlite.query(get_posts, user["id"], user["id"], user["id"])
    
    return render_template("stream.html.j2", title="Stream", username=username, form=post_form, posts=posts)


@app.route("/comments/<string:username>/<int:post_id>", methods=["GET", "POST"])
def comments(username: str, post_id: int):
    """Provides the comments page for the application.

    If a form was submitted, it reads the form data and inserts a new comment into the database.

    Otherwise, it reads the username and post id from the URL and displays all comments for the post.
    """
    comments_form = CommentsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if comments_form.is_submitted():
        clean_comment = bleach.clean(comments_form.comment.data)
        insert_comment = """
            INSERT INTO Comments (p_id, u_id, comment, creation_time)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP);
            """
        sqlite.query(insert_comment, (post_id, user["id"], clean_comment))

    get_post = """
        SELECT *
        FROM Posts AS p JOIN Users AS u ON p.u_id = u.id
        WHERE p.id = ?;
        """
    get_comments = """
        SELECT DISTINCT *
        FROM Comments AS c JOIN Users AS u ON c.u_id = u.id
        WHERE c.p_id=?
        ORDER BY c.creation_time DESC;
        """
    post = sqlite.query(get_post, one=True)
    comments = sqlite.query(get_comments, (post_id,))
    return render_template(
        "comments.html.j2", title="Comments", username=username, form=comments_form, post=post, comments=comments
    )


@app.route("/friends/<string:username>", methods=["GET", "POST"])
def friends(username: str):
    """Provides the friends page for the application.

    If a form was submitted, it reads the form data and inserts a new friend into the database.

    Otherwise, it reads the username from the URL and displays all friends of the user.
    """
    friends_form = FriendsForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if friends_form.is_submitted():
        get_friend = f"""
            SELECT *
            FROM Users
            WHERE username = '{friends_form.username.data}';
            """
        friend = sqlite.query(get_friend, one=True)
        get_friends = """
            SELECT f_id
            FROM Friends
            WHERE username = ?;
            """
        friend = sqlite.query(get_friend, friends_form.username.data, one=True)

        if friend is None:
            flash("User does not exist!", category="warning")
        elif friend["id"] == user["id"]:
            flash("You cannot be friends with yourself!", category="warning")
        elif friend["id"] in [friend["f_id"] for friend in friends]:
            flash("You are already friends with this user!", category="warning")
        else:
            insert_friend = f"""
                INSERT INTO Friends (u_id, f_id)
                VALUES ({user["id"]}, {friend["id"]});
                """
            sqlite.query(insert_friend)
            flash("Friend successfully added!", category="success")

    get_friends = f"""
        SELECT *
        FROM Friends AS f JOIN Users as u ON f.f_id = u.id
        WHERE f.u_id = {user["id"]} AND f.f_id != {user["id"]};
        """
    friends = sqlite.query(get_friends)
    return render_template("friends.html.j2", title="Friends", username=username, friends=friends, form=friends_form)


@app.route("/profile/<string:username>", methods=["GET", "POST"])
def profile(username: str):
    """Provides the profile page for the application.

    If a form was submitted, it reads the form data and updates the user's profile in the database.

    Otherwise, it reads the username from the URL and displays the user's profile.
    """
    profile_form = ProfileForm()
    get_user = f"""
        SELECT *
        FROM Users
        WHERE username = '{username}';
        """
    user = sqlite.query(get_user, one=True)

    if profile_form.is_submitted():
        update_profile = f"""
            UPDATE Users
            SET education='{profile_form.education.data}', employment='{profile_form.employment.data}',
                music='{profile_form.music.data}', movie='{profile_form.movie.data}',
                nationality='{profile_form.nationality.data}', birthday='{profile_form.birthday.data}'
            WHERE username='{username}';
            """
        sqlite.query(update_profile)
        return redirect(url_for("profile", username=username))

    return render_template("profile.html.j2", title="Profile", username=username, user=user, form=profile_form)


@app.route("/uploads/<string:filename>")
def uploads(filename):
    """Provides an endpoint for serving uploaded files."""
    return send_from_directory(Path(app.instance_path) / app.config["UPLOADS_FOLDER_PATH"], filename)
