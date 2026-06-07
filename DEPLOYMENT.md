# CodeForge — Deployment Guide

  ## Quick Start (Local Testing)

  ```bash
  pip install -r requirements.txt
  cp .env.example .env       # then fill in your real values
  python app.py
  ```

  Open http://localhost:5000

  ---

  ## Firebase Setup

  1. Go to https://console.firebase.google.com → project **codeforge-d3aa2**
  2. Enable **Authentication** → Sign-in methods → Google + Email/Password
  3. Enable **Firestore Database** → Start in production mode
  4. Go to **Project Settings → Service Accounts → Generate new private key**
  5. Open the downloaded JSON — copy values into your `.env`:
     - `FIREBASE_PRIVATE_KEY_ID` → `private_key_id`
     - `FIREBASE_PRIVATE_KEY` → `private_key` (copy entire value with \n)
     - `FIREBASE_CLIENT_EMAIL` → `client_email`
     - `FIREBASE_CLIENT_ID` → `client_id`

  ### Firestore Security Rules (Firestore → Rules)

  ```
  rules_version = '2';
  service cloud.firestore {
    match /databases/{database}/documents {
      match /users/{uid} {
        allow read, write: if request.auth != null && request.auth.uid == uid;
      }
      match /products/{id} {
        allow read: if resource.data.active == true;
      }
      match /reviews/{id} {
        allow read: if true;
        allow create: if request.auth != null;
      }
      match /orders/{id} {
        allow read: if request.auth != null && resource.data.uid == request.auth.uid;
      }
      match /notifications/{id} {
        allow read, write: if request.auth != null && resource.data.uid == request.auth.uid;
      }
      match /{document=**} {
        allow read, write: if false;
      }
    }
  }
  ```

  ---

  ## Razorpay Setup

  1. Sign up at https://razorpay.com
  2. Dashboard → Settings → API Keys → Generate keys
  3. Copy **Key ID** and **Key Secret** into `.env`

  ---

  ## Deploying on Render.com (Free tier available)

  1. Push this project to a GitHub repository
  2. Go to https://render.com → New Web Service → Connect repo
  3. Build Command: `pip install -r requirements.txt`
  4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
  5. Add all env vars from `.env.example` in Render's **Environment** tab

  ### Live domain:
  Your app will be at **https://codeforge.onrender.com** (or your custom domain)

  ---

  ## First Admin Setup

  1. Register on your live site with the email set in `SUPER_ADMIN_EMAIL`
  2. Log in — you are automatically granted super admin access
  3. Go to **/admin** to access the panel

  ---

  ## Image Uploads

  1. Sign up at https://imgbb.com → API → Get API key
  2. Add key in Admin → Settings → ImgBB API Key
     OR set `IMGBB_API_KEY` env var

  ---

  ## AI Assistant

  1. Get OpenAI API key from https://platform.openai.com
  2. Set `OPENAI_API_KEY` env var
  3. Enable in Admin → AI Settings

  ---

  ## Project Structure

  ```
  codeforge/
  ├── app.py              ← All routes (flat, no blueprints)
  ├── firebase_config.py  ← Firebase Admin SDK init
  ├── requirements.txt
  ├── render.yaml         ← Render.com deployment config
  ├── .env.example        ← Copy to .env and fill in values
  ├── templates/
  │   ├── base.html       ← Global layout, header, footer
  │   ├── index.html
  │   ├── marketplace.html
  │   ├── product.html
  │   ├── login.html / register.html
  │   ├── dashboard.html / orders.html / profile.html
  │   ├── wishlist.html / notifications.html
  │   ├── custom_order.html / ai_chat.html
  │   ├── contact.html / legal.html
  │   ├── partials/card.html, sidebar.html
  │   └── admin/          ← All admin templates
  │       ├── base.html   ← Admin layout
  │       ├── dashboard.html, products.html, product_form.html
  │       ├── orders.html, custom_orders.html, users.html
  │       ├── coupons.html, analytics.html, legal.html
  │       ├── ai.html, settings.html, admins.html
  │       └── backup.html, logs.html, categories.html
  └── static/
      ├── css/style.css   ← Main design system
      ├── css/admin.css   ← Admin panel styles
      └── js/app.js       ← Global JS
  ```
  