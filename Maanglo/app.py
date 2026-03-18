from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime
from config import Config
from functools import wraps

app = Flask(__name__)
app.config.from_object(Config)

mongo = PyMongo(app)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login to continue.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email    = request.form.get('email').strip().lower()
        phone    = request.form.get('phone').strip()
        password = request.form.get('password')
        role     = request.form.get('role')

        if not all([username, email, phone, password, role]):
            flash('All fields are required.', 'error')
            return redirect(url_for('register'))

        if mongo.db.users.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('register'))

        mongo.db.users.insert_one({
            'username': username,
            'email':    email,
            'phone':    phone,
            'password': generate_password_hash(password),
            'role':     role
        })

        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))

    role = request.args.get('role', 'buyer')
    return render_template('register.html', selected_role=role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email').strip().lower()
        password = request.form.get('password')
        user     = mongo.db.users.find_one({'email': email})

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role']     = user['role']

        flash(f"Welcome back, {user['username']}!", 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')

    if role == 'buyer':
        requests = list(mongo.db.requests.find(
            {'buyer_id': session['user_id']}
        ).sort('created_at', -1))

        for r in requests:
            r['offer_count'] = mongo.db.offers.count_documents({'request_id': str(r['_id'])})

        return render_template('dashboard.html', requests=requests, role=role)

    elif role == 'seller':
        all_requests = list(mongo.db.requests.find().sort('created_at', -1))

        for r in all_requests:
            r['offer_count'] = mongo.db.offers.count_documents({'request_id': str(r['_id'])})
            existing_offer = mongo.db.offers.find_one({
                'request_id': str(r['_id']),
                'seller_id':  session['user_id']
            })
            r['already_offered'] = existing_offer is not None
            r['my_offer_id']     = str(existing_offer['_id']) if existing_offer else None
            r['my_offer_status'] = existing_offer['status'] if existing_offer else None

        return render_template('dashboard.html', requests=all_requests, role=role)

@app.route('/post-need', methods=['GET', 'POST'])
@login_required
def post_need():
    if session.get('role') != 'buyer':
        flash('Only buyers can post a need.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title       = request.form.get('title').strip()
        description = request.form.get('description').strip()
        category    = request.form.get('category')
        budget      = request.form.get('budget').strip()
        location    = request.form.get('location').strip()

        if not all([title, description, category, budget, location]):
            flash('All fields are required.', 'error')
            return redirect(url_for('post_need'))

        mongo.db.requests.insert_one({
            'buyer_id':    session['user_id'],
            'buyer_name':  session['username'],
            'title':       title,
            'description': description,
            'category':    category,
            'budget':      budget,
            'location':    location,
            'status':      'open',
            'created_at':  datetime.utcnow()
        })

        flash('Your need has been posted!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('post_need.html')

@app.route('/make-offer/<request_id>', methods=['GET', 'POST'])
@login_required
def make_offer(request_id):
    if session.get('role') != 'seller':
        flash('Only sellers can make offers.', 'error')
        return redirect(url_for('dashboard'))

    buy_request = mongo.db.requests.find_one({'_id': ObjectId(request_id)})
    if not buy_request:
        flash('Request not found.', 'error')
        return redirect(url_for('dashboard'))

    already_offered = mongo.db.offers.find_one({
        'request_id': request_id,
        'seller_id':  session['user_id']
    })
    if already_offered:
        flash('You have already made an offer on this request.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        price       = request.form.get('price').strip()
        description = request.form.get('description').strip()
        delivery    = request.form.get('delivery').strip()

        if not all([price, description, delivery]):
            flash('All fields are required.', 'error')
            return redirect(url_for('make_offer', request_id=request_id))

        mongo.db.offers.insert_one({
            'request_id':  request_id,
            'seller_id':   session['user_id'],
            'seller_name': session['username'],
            'price':       price,
            'description': description,
            'delivery':    delivery,
            'status':      'pending',
            'created_at':  datetime.utcnow()
        })

        flash('Your offer has been submitted!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('make_offer.html', buy_request=buy_request)

@app.route('/view-offers/<request_id>')
@login_required
def view_offers(request_id):
    if session.get('role') != 'buyer':
        flash('Only buyers can view offers.', 'error')
        return redirect(url_for('dashboard'))

    buy_request = mongo.db.requests.find_one({'_id': ObjectId(request_id)})
    if not buy_request:
        flash('Request not found.', 'error')
        return redirect(url_for('dashboard'))

    offers = list(mongo.db.offers.find(
        {'request_id': request_id}
    ).sort('created_at', -1))

    return render_template('view_offers.html', buy_request=buy_request, offers=offers)

@app.route('/accept-offer/<offer_id>', methods=['POST'])
@login_required
def accept_offer(offer_id):
    if session.get('role') != 'buyer':
        flash('Only buyers can accept offers.', 'error')
        return redirect(url_for('dashboard'))

    offer = mongo.db.offers.find_one({'_id': ObjectId(offer_id)})
    if not offer:
        flash('Offer not found.', 'error')
        return redirect(url_for('dashboard'))

    buy_request = mongo.db.requests.find_one({'_id': ObjectId(offer['request_id'])})
    if buy_request['buyer_id'] != session['user_id']:
        flash('You are not authorized to accept this offer.', 'error')
        return redirect(url_for('dashboard'))

    mongo.db.offers.update_one(
        {'_id': ObjectId(offer_id)},
        {'$set': {'status': 'accepted'}}
    )

    mongo.db.offers.update_many(
        {'request_id': offer['request_id'], '_id': {'$ne': ObjectId(offer_id)}},
        {'$set': {'status': 'rejected'}}
    )

    mongo.db.requests.update_one(
        {'_id': ObjectId(offer['request_id'])},
        {'$set': {'status': 'closed'}}
    )

    flash('Offer accepted! The deal is on. 🎉', 'success')
    return redirect(url_for('view_offers', request_id=offer['request_id']))

@app.route('/chat/<offer_id>', methods=['GET', 'POST'])
@login_required
def chat(offer_id):
    offer = mongo.db.offers.find_one({'_id': ObjectId(offer_id)})
    if not offer:
        flash('Offer not found.', 'error')
        return redirect(url_for('dashboard'))

    buy_request = mongo.db.requests.find_one({'_id': ObjectId(offer['request_id'])})

    user_id   = session['user_id']
    is_buyer  = user_id == buy_request['buyer_id']
    is_seller = user_id == offer['seller_id']

    if not is_buyer and not is_seller:
        flash('You are not authorized to view this chat.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            mongo.db.chats.insert_one({
                'offer_id':    offer_id,
                'sender_id':   user_id,
                'sender_name': session['username'],
                'message':     message,
                'created_at':  datetime.utcnow()
            })
        return redirect(url_for('chat', offer_id=offer_id))

    messages = list(mongo.db.chats.find(
        {'offer_id': offer_id}
    ).sort('created_at', 1))

    return render_template('chat.html',
        offer=offer,
        buy_request=buy_request,
        messages=messages,
        is_buyer=is_buyer
    )

@app.route('/ping-db')
def ping_db():
    try:
        mongo.db.command('ping')
        return {'status': 'ok', 'message': 'MongoDB connected successfully!'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True) 