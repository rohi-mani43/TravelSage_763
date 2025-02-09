from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import requests
import google.generativeai as genai
from geopy.geocoders import Nominatim
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
import json
from decimal import Decimal
from cryptography.fernet import Fernet
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(16))

# API Keys and Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', Fernet.generate_key())

# Initialize encryption
fernet = Fernet(ENCRYPTION_KEY)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')
# Smart Contract ABI
CONTRACT_ABI = [
    {
        "inputs": [{"name": "destination", "type": "string"}],
        "name": "makePayment",
        "type": "function",
        "stateMutability": "payable"
    },
    {
        "inputs": [],
        "name": "getPaymentHistory",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view"
    }
]

class BlockchainPayment:
    def __init__(self):
        try:
            self.w3 = Web3(Web3.HTTPProvider(f'https://sepolia.infura.io/v3/{INFURA_PROJECT_ID}'))
            if not self.w3.is_connected():
                raise Exception("Failed to connect to Ethereum network")
            self.contract_address = os.getenv('SMART_CONTRACT_ADDRESS')
            if self.contract_address:
                self.contract = self.w3.eth.contract(address=self.contract_address, abi=CONTRACT_ABI)
        except Exception as e:
            print(f"Blockchain initialization error: {str(e)}")
            self.w3 = None

    def process_payment(self, from_address, private_key, amount, to_address, destination):
        try:
            if not self.w3:
                raise Exception("Web3 not initialized")
            
            if not Web3.is_address(to_address):
                raise ValueError("Invalid destination address")

            nonce = self.w3.eth.get_transaction_count(from_address)
            gas_price = self.w3.eth.gas_price
            gas_limit = 21000  # Standard ETH transfer gas limit

            # Convert amount to Wei
            amount_wei = self.w3.to_wei(amount, 'ether')

            # Prepare transaction data
            if self.contract:
                # If using smart contract
                contract_data = self.contract.functions.makePayment(destination).build_transaction({
                    'chainId': 11155111,  # Sepolia chain ID
                    'gas': gas_limit,
                    'gasPrice': gas_price,
                    'nonce': nonce,
                    'from': from_address,
                    'value': amount_wei
                })
                transaction = contract_data
            else:
                # Direct ETH transfer
                transaction = {
                    'nonce': nonce,
                    'gasPrice': gas_price,
                    'gas': gas_limit,
                    'to': to_address,
                    'value': amount_wei,
                    'data': b'',
                    'chainId': 11155111  # Sepolia chain ID
                }

            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            return {
                'status': 'success',
                'transaction_hash': receipt['transactionHash'].hex(),
                'block_number': receipt['blockNumber']
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }

class AITravelPlanner:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="travel_companion")

    def get_location_details(self, location):
        try:
            loc = self.geolocator.geocode(location, addressdetails=True)
            return loc
        except Exception:
            return None

    def get_weather(self, lat, lon):
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
            response = requests.get(url)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def generate_ai_recommendations(self, location, interests, budget, duration, weather):
        prompt = f"""
        As a travel expert, create a detailed travel plan for {location} with the following details:
        - Duration: {duration} days
        - Budget: USD {budget}
        - Interests: {', '.join(interests)}
        - Current Weather: {weather}
        
        Please provide:
        1. Day-by-day itinerary
        2. Estimated costs for each activity
        3. Local transportation options
        4. Student-friendly recommendations
        5. Must-visit locations
        6. Local food recommendations
        7. Safety tips
        8. Time management suggestions
        """
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            return None

def init_db():
    conn = sqlite3.connect('travel_companion.db')
    c = conn.cursor()
    
    # Users table with simplified structure
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            mobile TEXT NOT NULL,
            wallet_address TEXT DEFAULT '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
            wallet_private_key TEXT DEFAULT '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            last_login DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    
    # Transactions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            transaction_hash TEXT UNIQUE,
            amount DECIMAL(18,8),
            destination_address TEXT,
            status TEXT,
            error_message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Travel Plans table
    c.execute('''
        CREATE TABLE IF NOT EXISTS travel_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            destination TEXT,
            journey_date DATE,
            duration INTEGER,
            budget DECIMAL(10,2),
            status TEXT,
            weather_info TEXT,
            recommendations TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect('travel_companion.db')
    conn.row_factory = sqlite3.Row
    return conn
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password = request.form['password']
            mobile = request.form['mobile'].strip()
            
            # Default wallet address for all users
            default_wallet = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
            
            if not all([username, password, mobile]):
                flash('All fields are required')
                return render_template('register.html')
            
            if not mobile.isdigit() or len(mobile) != 10:
                flash('Please enter a valid 10-digit mobile number')
                return render_template('register.html')
            
            conn = get_db()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    flash('Username already exists')
                    return render_template('register.html')
                
                cursor.execute("""
                    INSERT INTO users (username, password, mobile, wallet_address, created_at) 
                    VALUES (?, ?, ?, ?, ?)
                    """, (
                        username,
                        generate_password_hash(password),
                        mobile,
                        default_wallet,
                        datetime.now()
                    ))
                conn.commit()
                flash('Registration successful! Please login.')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Registration failed - please try again')
            finally:
                conn.close()
                
        except Exception as e:
            flash(f'Registration failed: {str(e)}')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password = request.form['password']
            
            if not username or not password:
                flash('Please enter both username and password')
                return render_template('login.html')
            
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, password
                FROM users 
                WHERE username = ?
            """, (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user['password'], password):
                cursor.execute("""
                    UPDATE users 
                    SET last_login = ? 
                    WHERE id = ?
                """, (datetime.now(), user['id']))
                conn.commit()
                
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['login_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                return redirect(url_for('layout'))
            else:
                flash('Invalid username or password')
        except Exception as e:
            flash(f'Login failed: {str(e)}')
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/layout')
def layout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('layout.html')

@app.route('/plan_trip', methods=['POST'])
def plan_trip():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        current_location = request.form['current_location'].strip()
        destination = request.form['destination'].strip()
        journey_date = request.form['journey_date']
        
        # Add validation for empty or non-numeric values
        try:
            duration = int(request.form.get('duration', '0').strip())
        except (ValueError, TypeError):
            flash("Please enter a valid duration")
            return render_template("layout.html")

        try:
            budget = float(request.form.get('budget', '0').strip())
        except (ValueError, TypeError):
            flash("Please enter a valid budget amount")
            return render_template("layout.html")
            
        interests = request.form.getlist('interests')

        # Validate required fields
        if not all([current_location, destination, journey_date]):
            flash("Please fill in all required fields.")
            return render_template("layout.html")

        if duration <= 0:
            flash("Duration must be at least 1 day")
            return render_template("layout.html")

        if budget <= 0:
            flash("Budget must be greater than 0")
            return render_template("layout.html")


        planner = AITravelPlanner()
        dest_loc = planner.get_location_details(destination)
        
        if not dest_loc:
            flash("Could not find destination location")
            return render_template('layout.html')

        weather_data = planner.get_weather(dest_loc.latitude, dest_loc.longitude)
        weather_desc = "Unavailable"
        temp = None

        if weather_data and 'weather' in weather_data and 'main' in weather_data:
            weather_desc = weather_data['weather'][0]['description']
            temp = weather_data['main']['temp']

        recommendations = planner.generate_ai_recommendations(
            destination, interests, budget, duration, weather_desc
        )

        if not recommendations:
            flash("Failed to generate travel recommendations")
            return render_template("layout.html")

        current_time = datetime.now()
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO travel_plans (
                    user_id, destination, journey_date, duration, 
                    budget, status, weather_info, recommendations,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session['user_id'], destination, journey_date, duration,
                budget, 'planned', json.dumps(weather_data), recommendations,
                current_time, current_time
            ))
            conn.commit()
            plan_id = cursor.lastrowid

            sections = [
                {
                    "title": sec.split('\n')[0],
                    "content": '\n'.join(sec.split('\n')[1:])
                }
                for sec in recommendations.split('\n\n') if sec.strip()
            ]

            return render_template(
                "plan_result.html",
                plan_id=plan_id,
                destination=destination,
                journey_date=journey_date,
                duration=duration,
                budget=budget,
                weather_desc=weather_desc,
                temp=temp,
                sections=sections
            )

        except Exception as e:
            conn.rollback()
            flash(f"Error saving travel plan: {str(e)}")
            return render_template('layout.html')
        finally:
            conn.close()

    except Exception as e:
        flash(f"Error planning trip: {str(e)}")
        return render_template('layout.html')

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Please login first'}), 401
    
    try:
        amount = float(request.form['amount'])
        destination_address = request.form['destination_address'].strip()
        
        # Properly handle plan_id conversion
        try:
            plan_id = int(request.form.get('plan_id', 0))  # Default to 0 if not provided
        except (ValueError, TypeError):
            plan_id = 0  # Set to 0 if conversion fails
            
        destination = request.form.get('destination', 'Unknown')
        
        blockchain = BlockchainPayment()
        
        # Get user's wallet info
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT wallet_address, wallet_private_key 
                FROM users 
                WHERE id = ?""", (session['user_id'],))
            user = cursor.fetchone()
            
            if not user:
                flash('User wallet information not found')
                return redirect(url_for('layout'))  # Redirect to layout if no plan_id
            
            
            
            # Process payment
            payment_result = blockchain.process_payment(
                user['wallet_address'],
                user['wallet_private_key'],
                amount,
                destination_address,
                destination
            )
            
            if payment_result['status'] == 'success':
                # Record successful transaction
                cursor.execute("""
                    INSERT INTO transactions (
                        user_id, transaction_hash, amount, 
                        destination_address, status
                    )
                    VALUES (?, ?, ?, ?, ?)""",
                    (session['user_id'], payment_result['transaction_hash'],
                     amount, destination_address, 'completed'))
                
                # Update plan status if plan_id exists and is valid
                if plan_id > 0:
                    cursor.execute("""
                        UPDATE travel_plans 
                        SET status = 'paid', updated_at = ? 
                        WHERE id = ? AND user_id = ?""",
                        (datetime.now(), plan_id, session['user_id']))
                
                conn.commit()
                flash('Payment processed successfully! Transaction Hash: ' + 
                      payment_result['transaction_hash'])
                return redirect(url_for('transaction_history'))
            else:
                # Record failed transaction
                cursor.execute("""
                    INSERT INTO transactions (
                        user_id, amount, destination_address, 
                        status, error_message
                    )
                    VALUES (?, ?, ?, ?, ?)""",
                    (session['user_id'], amount, destination_address,
                     'failed', payment_result.get('message', 'Unknown error')))
                conn.commit()
                flash('Payment failed: ' + payment_result.get('message', 'Unknown error'))
                
        except Exception as e:
            conn.rollback()
            flash('Error processing payment: ' + str(e))
        finally:
            conn.close()
            
    except Exception as e:
        flash('Error processing payment: ' + str(e))
    
    # Final redirect with proper handling of plan_id
    if plan_id > 0:
        return redirect(url_for('plan_result', plan_id=plan_id))
    return redirect(url_for('layout'))


@app.route('/transaction_history')
def transaction_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get all transactions with plan details
        cursor.execute("""
            SELECT 
                t.*,
                p.destination,
                p.journey_date,
                p.status as plan_status
            FROM transactions t
            LEFT JOIN travel_plans p ON t.user_id = p.user_id
            WHERE t.user_id = ? 
            ORDER BY t.timestamp DESC""", (session['user_id'],))
        
        transactions = cursor.fetchall()
        
        return render_template('transaction_history.html', 
                             transactions=transactions,
                             current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    except Exception as e:
        flash(f'Error loading transaction history: {str(e)}')
        return redirect(url_for('layout'))
    finally:
        conn.close()

@app.route('/plan_result/<int:plan_id>')
def plan_result(plan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get complete plan details
        cursor.execute("""
            SELECT 
                p.*,
                u.wallet_address
            FROM travel_plans p
            JOIN users u ON p.user_id = u.id
            WHERE p.id = ? AND p.user_id = ?""", 
            (plan_id, session['user_id']))
        plan = cursor.fetchone()
        
        if not plan:
            flash('Plan not found')
            return redirect(url_for('layout'))
        
        # Parse stored data
        weather_data = json.loads(plan['weather_info']) if plan['weather_info'] else {}
        recommendations = plan['recommendations']
        
        # Process recommendations into sections
        sections = [
            {
                "title": sec.split('\n')[0],
                "content": '\n'.join(sec.split('\n')[1:])
            }
            for sec in recommendations.split('\n\n') if sec.strip()
        ] if recommendations else []
        
        return render_template(
            'plan_result.html',
            plan=plan,
            weather_data=weather_data,
            sections=sections,
            wallet_address=session.get('wallet_address'),
            current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
    except Exception as e:
        flash(f'Error loading plan: {str(e)}')
        return redirect(url_for('layout'))
    finally:
        conn.close()

@app.route('/logout')
def logout():
    try:
        # Update last login time before logging out
        if 'user_id' in session:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET last_login = ? 
                WHERE id = ?""", 
                (datetime.now(), session['user_id']))
            conn.commit()
            conn.close()
        
        # Clear session
        session.clear()
        flash('You have been logged out successfully')
    except Exception as e:
        flash(f'Error during logout: {str(e)}')
    
    return redirect(url_for('home'))

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# Context processor for global template variables
@app.context_processor
def utility_processor():
    def format_datetime(dt):
        if isinstance(dt, str):
            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    return dict(format_datetime=format_datetime)

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Set up logging (optional)
    if not app.debug:
        import logging
        from logging.handlers import RotatingFileHandler
        
        if not os.path.exists('logs'):
            os.mkdir('logs')
            
        file_handler = RotatingFileHandler(
            'logs/travel_companion.log',
            maxBytes=10240,
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Travel Companion startup')
    
    # Run the application
    app.run(debug=True)
