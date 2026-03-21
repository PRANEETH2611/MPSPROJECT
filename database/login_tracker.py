"""
MongoDB Login Tracker - Only for tracking user logins
"""
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime

class LoginTracker:
    """MongoDB Connection for Login Tracking Only"""
    
    def __init__(self, connection_string=None, database_name="aiops_db"):
        """
        Initialize MongoDB connection for login tracking
        
        Args:
            connection_string: MongoDB connection string (default: mongodb://localhost:27017/)
            database_name: Name of the database to use
        """
        if connection_string is None:
            connection_string = os.getenv(
                'MONGODB_URI', 
                'mongodb://localhost:27017/'
            )
        
        self.connection_string = connection_string
        self.database_name = database_name
        self.client = None
        self.db = None
        self._connect()
    
    def _connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000
            )
            self.client.server_info()
            self.db = self.client[self.database_name]
            self.logins_collection = self.db["user_logins"]
            
            # Create index on timestamp for faster queries
            self.logins_collection.create_index("timestamp")
            self.logins_collection.create_index("username")
            
            print("[OK] Connected to MongoDB for login tracking")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"[WARN] MongoDB connection failed: {e}")
            print("[INFO] Login tracking will be disabled. Dashboard will still work.")
            self.client = None
            self.db = None
    
    def log_login(self, username, role, ip_address=None, user_agent=None):
        """Log a user login"""
        if self.db is None:
            return False
        
        try:
            login_record = {
                "username": username,
                "role": role,
                "timestamp": datetime.now(),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "status": "success"
            }
            self.logins_collection.insert_one(login_record)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to log login: {e}")
            return False
    
    def log_failed_login(self, username, ip_address=None, user_agent=None):
        """Log a failed login attempt"""
        if self.db is None:
            return False
        
        try:
            login_record = {
                "username": username,
                "role": None,
                "timestamp": datetime.now(),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "status": "failed"
            }
            self.logins_collection.insert_one(login_record)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to log failed login: {e}")
            return False
    
    def get_recent_logins(self, limit=10):
        """Get recent login records"""
        if self.db is None:
            return []
        
        try:
            logins = list(self.logins_collection.find(
                {"status": "success"}
            ).sort("timestamp", -1).limit(limit))
            
            # Convert ObjectId to string and datetime to ISO
            for login in logins:
                login['_id'] = str(login['_id'])
                if isinstance(login.get('timestamp'), datetime):
                    login['timestamp'] = login['timestamp'].isoformat()
            
            return logins
        except Exception as e:
            print(f"[ERROR] Failed to get logins: {e}")
            return []
    
    def get_login_stats(self):
        """Get login statistics"""
        if self.db is None:
            return {}
        
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": "$username",
                        "total_logins": {"$sum": 1},
                        "last_login": {"$max": "$timestamp"}
                    }
                },
                {"$sort": {"total_logins": -1}}
            ]
            
            stats = list(self.logins_collection.aggregate(pipeline))
            
            # Convert to dict format
            result = {}
            for stat in stats:
                result[stat['_id']] = {
                    "total_logins": stat['total_logins'],
                    "last_login": stat['last_login'].isoformat() if isinstance(stat['last_login'], datetime) else stat['last_login']
                }
            
            return result
        except Exception as e:
            print(f"[ERROR] Failed to get login stats: {e}")
            return {}
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()


# Singleton instance
_login_tracker = None

def get_login_tracker(connection_string=None):
    """Get login tracker instance (singleton pattern)"""
    global _login_tracker
    if _login_tracker is None:
        _login_tracker = LoginTracker(connection_string)
    return _login_tracker
