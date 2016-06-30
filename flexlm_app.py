#!/usr/bin/env python2

import os
from datetime import datetime
from flask import Flask, render_template, session, redirect, url_for, Response, flash
from flask import abort
from flask.ext.script import Manager
from flask.ext.bootstrap import Bootstrap
from flask.ext.moment import Moment
from flask.ext.wtf import Form
from flask.ext.login import LoginManager, UserMixin
from flask.ext.login import login_required, current_user, login_user, logout_user
from wtforms import StringField, FileField, SubmitField, IntegerField, PasswordField
from wtforms import ValidationError, widgets, SelectMultipleField, BooleanField
from wtforms.validators import Required
from flask.ext.sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import json
import flexlm_parser
import rrdfetch
import pdb

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'hard to guess string'
app.config['SQLALCHEMY_DATABASE_URI'] =\
    'sqlite:///' + os.path.join(basedir, 'data.sqlite')
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.debug = True

manager = Manager(app)
bootstrap = Bootstrap(app)
db = SQLAlchemy(app)
moment = Moment(app)
login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

#-------------------------------------------------------------------
# Database Models for SQLAlchemy
#-------------------------------------------------------------------
class Server(db.Model):
    __tablename__ = 'servers'
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(50), unique=True)
    server = db.Column(db.String(64))
    port = db.Column(db.Integer)
    software = db.Column(db.String(50))
    rrd_file = db.Column(db.String(255))
    columns = db.relationship('Columns', backref='servers')

    def __repr__(self):
        return '<Server %r>' % self.vendor

class Columns(db.Model):
    __tablename__ = 'columns'
    id = db.Column(db.Integer, primary_key=True)
    columns = db.Column(db.String(50))
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'))

    def __repr__(self):
        return '<Columns %r>' % self.columns

#-------------------------------------------------------------------
# Authentication implentation and SQLAlchemy model
# This database model has been taken from the book flask web development by
# Miguel Grinberg
#-------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return '<User %r>' % self.username

@login_manager.user_loader
def user_loader(user_id):
        return User.query.get(int(user_id))

#-------------------------------------------------------------------
# Forms
#-------------------------------------------------------------------

class baseForm(Form):
    vendor = StringField('Vendor', validators=[Required()])
    port = IntegerField('Port Number', validators=[Required()])
    server = StringField('License Server Name', validators=[Required()])
    software_feature = StringField('Software To Monitor')
    rrd_file = StringField('Full Path To RRD Usage Database')
    
    def validate_vendor(self, field):
        if Server.query.filter_by(vendor=field.data).first():
            raise ValidationError('Vendor name already used')

    def validate_rrd_file(self, field):
        # Check if the data is empty ok then if not check if it exists
        if field.data == '':
            pass 
        elif os.path.isfile(field.data) is False:
            raise ValidationError('File does not exist')
            if field.data[-3:] != 'rrd':
                raise ValueError('File is not a RRD database')

    def validate_columns(self, field):
        for column_name in field.data.split(','):
            if column_name not in rrdfetch.header(self.rrd_file.data):
                raise ValueError (rrdfetch.header(self.rrd_file.data))

class AddServerForm(baseForm):
    submit = SubmitField('Add Server')

class LoginForm(Form):
    user_name = StringField('User Name', validators=[Required()])
    password = PasswordField('Password', validators=[Required()])
    submit = SubmitField('Log in')
    
class ChangePasswordForm():
    pass

#-------------------------------------------------------------------
# Routes
#-------------------------------------------------------------------

@app.route('/')
def index():
    #pdb.set_trace()
    servers = Server.query.all()
    return render_template('index.html', servers=servers)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.user_name.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user)
            #pdb.set_trace()
            return redirect(url_for('index'))
    flash('Invalid username or password.') 
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/servers/config', methods=['GET', 'POST'])
@login_required
def config():
    form = AddServerForm()
    if form.validate_on_submit():
        session['vendor'] = form.vendor.data
        session['port'] = form.port.data
        session['server'] = form.server.data
        session['software_feature'] = form.software_feature.data
        session['rrd_file'] = form.rrd_file.data
        record = Server(vendor=session.get('vendor'), 
                        port=session.get('port'),
                        server=session.get('server'),
                        software=session.get('software_feature'),
                        rrd_file=session.get('rrd_file'))
        # Commit to the database
        db.session.add(record)
        #db.session.add(column_record)
        db.session.commit()
        if session.get('rrd_file') is not None:
            return redirect(url_for('edit',
                                   vendor=session.get('vendor')))
        else:
            return redirect(url_for('index'))
    return render_template('config.html', form=form)

@app.route('/servers/config/<vendor>', methods=['GET', 'POST'])
@login_required
def edit(vendor):
    settings = Server.query.filter_by(vendor=vendor).first()
    if settings is None:
        abort(404)                        

    if settings.rrd_file != '':
        initial_has_rrd_file = True
        header = rrdfetch.header(settings.rrd_file)
        columns = [row.columns for row in settings.columns]
    else:
        initial_has_rrd_file = False

    class EditForm(baseForm):
        # Override the validator for the basefrom
        # Want to make sure that we can accept the data by 
        # relaxing the fact that the vendor is unique.
        def validate_vendor(self, field):
            if field.data == '':
                raise ValidationError('Required Field')

    if initial_has_rrd_file is True:
        # Dynamically create the fields based on column names
        # And check if they are in the database
        for column_name in header:
            checkbox_name = column_name
            if column_name in columns:
                setattr(EditForm, checkbox_name, 
                        BooleanField(label=column_name, default=True))
            else:
                setattr(EditForm, checkbox_name, 
                        BooleanField(label=column_name))
    
    setattr(EditForm, 'submit', SubmitField('Update'))

    form = EditForm(port=settings.port, vendor=settings.vendor, 
                    server=settings.server, 
                    software_feature=settings.software, 
                    rrd_file=settings.rrd_file)

    if form.validate_on_submit():
        record = Server.query.filter_by(vendor=vendor).first()
        # Deal with form that has the column names.
        if initial_has_rrd_file is True:
            # Clear out the current options then add the new ones.
            for column_name in header:
                column_record = Columns.query.filter_by(
                    columns=column_name, 
                    server_id=settings.id).first()
                checkbox_state = getattr(form, column_name).data
                # Test the checkbox
                if checkbox_state is True and column_record is None:
                    record.columns.append(Columns(columns=column_name))
                    db.session.add(record)
                elif checkbox_state is False and column_record is not None:
                    db.session.delete(column_record)

        # Deal with the rest of the data to be updated
        record.vendor = form.vendor.data
        record.port = form.port.data
        record.server = form.server.data
        record.software_feature = form.software_feature.data
        
        # Check to see if the rrd file has been changed 
        # if so:
        # Delete all of the column names in the columns table
        # then return this page with the new headers if any
        # headers 
        if record.rrd_file != form.rrd_file.data:
            Columns.query.filter_by(server_id=record.id).delete()
            record.rrd_file = form.rrd_file.data
            db.session.commit()
            return redirect(url_for('edit', vendor=vendor))
        else:
            db.session.commit()
            return redirect(url_for('index'))

    return render_template('config.html', form=form, 
                           vendor=vendor)

@app.route('/servers/users/<vendor>')
def users(vendor):
    settings = Server.query.filter_by(vendor=vendor).first() 
    if settings is None:
        abort(404)
    server = str(settings.port) +'@'+ settings.server
    users = flexlm_parser.get_licenses(server, settings.software)

    return render_template('users.html', vendor=vendor, users=users, 
                           current_time=datetime.utcnow())
    
    
    return render_template('users.html', vendor=vendor)

@app.route('/servers/delete/<vendor>')
@login_required
def delete(vendor):
    settings = Server.query.filter_by(vendor=vendor).first()
    if settings is None:
        abort(404)
    else:
        Server.query.filter_by(vendor=settings.vendor).delete()
        # Delete Columns so they are not orphaned
        Columns.query.filter_by(server_id=settings.id).delete()
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/servers/usage/data/<vendor>/<time_peroid>')
def usage(vendor, time_peroid):
    settings = Server.query.filter_by(vendor=vendor).first()
    if settings is None:
        abort(404)
    columns = [row.columns for row in settings.columns]
    # rrdtool bindings does not like unicode convert to str
    try:
        data = rrdfetch.package_data(settings.rrd_file, time_peroid, 
                                     columns)
    except:
        abort(500)
    #return jsonify(data[0]) # should do it this way
    return Response(json.dumps(data, sort_keys=True),
                    mimetype='application/json')

@app.route('/servers/usage/<vendor>')
@app.route('/servers/usage/<vendor>/')
@app.route('/servers/usage/<vendor>/<time_peroid>')
def chart(vendor, time_peroid='24h'):
    settings = Server.query.filter_by(vendor=vendor).first()
    if settings is None:
        abort(404)
    return render_template('usage.html', vendor=vendor, 
                           current_time=datetime.utcnow(), 
                           time_peroid=time_peroid)

@login_manager.unauthorized_handler
def unauthorized_handler():
    return render_template('401.html'), 401

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def page_not_found(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    manager.run()
