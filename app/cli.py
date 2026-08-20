import click
from flask import current_app
from app.auth.service import create_admin,create_teacher
from app.email.service import process_pending
from app.database import get_db

def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--name",prompt=True)
    @click.option("--email",prompt=True)
    @click.option("--password",prompt=True,hide_input=True,confirmation_prompt=True)
    def cmd_create_admin(name,email,password):
        db=get_db()
        if db.execute("SELECT 1 FROM admins LIMIT 1").fetchone(): raise click.ClickException("An admin already exists")
        click.echo(f"Admin created: {create_admin(name,email,password)}")
    @app.cli.command("create-teacher")
    @click.option("--name",prompt=True)
    @click.option("--email",prompt=True)
    @click.option("--password",prompt=True,hide_input=True,confirmation_prompt=True)
    def cmd_create_teacher(name,email,password): click.echo(f"Teacher created: {create_teacher(name,email,password)}")
    @app.cli.command("process-email-jobs")
    @click.option("--limit",default=50,type=int)
    def cmd_email(limit): click.echo(process_pending(limit))
