import os
  import firebase_admin
  from firebase_admin import credentials, firestore, auth as fa

  _initialized = False
  db = None

  def init_firebase():
      global _initialized, db
      if _initialized:
          return
      private_key = os.environ.get('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n')
      cred = credentials.Certificate({
          "type": "service_account",
          "project_id": os.environ.get('FIREBASE_PROJECT_ID', 'codeforge-d3aa2'),
          "private_key_id": os.environ.get('FIREBASE_PRIVATE_KEY_ID', ''),
          "private_key": private_key,
          "client_email": os.environ.get('FIREBASE_CLIENT_EMAIL', ''),
          "client_id": os.environ.get('FIREBASE_CLIENT_ID', ''),
          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
          "token_uri": "https://oauth2.googleapis.com/token",
          "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      })
      firebase_admin.initialize_app(cred, {
          'databaseURL': os.environ.get('FIREBASE_DATABASE_URL', 'https://codeforge-d3aa2-default-rtdb.firebaseio.com')
      })
      db = firestore.client()
      _initialized = True

  def get_db():
      global db
      if not _initialized:
          init_firebase()
      return db

  def get_auth():
      if not _initialized:
          init_firebase()
      return fa
  