from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

def connexion_db():
    conn = sqlite3.connect("quincaillerie_reseau.db")
    conn.row_factory = sqlite3.Row
    return conn

# Préparation automatique de la base de données de la quincaillerie
with connexion_db() as conn:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS quincaillerie (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT UNIQUE NOT NULL,
        quantite_initiale INTEGER DEFAULT 0,
        quantite_ajoutee INTEGER DEFAULT 0,
        quantite_vendue INTEGER DEFAULT 0,
        prix_achat REAL DEFAULT 0.0,
        prix_vente REAL DEFAULT 0.0
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ventes_historique (
        id_facture TEXT NOT NULL,
        date_vente TEXT NOT NULL,
        article_nom TEXT NOT NULL,
        quantite_vendue INTEGER NOT NULL,
        prix_unitaire REAL NOT NULL,
        total_paye REAL NOT NULL
    )
    """)

@app.route('/')
def tableau_de_bord():
    """Affiche la page d'accueil visuelle (index.html)"""
    return render_template('index.html')

@app.route('/api/donnies_patron')
def api_donnies_patron():
    """Calcule et renvoie toutes les statistiques financières et de stocks pour le patron."""
    conn = connexion_db()
    articles = conn.execute("SELECT * FROM quincaillerie").fetchall()
    conn.close()
    
    total_ca = 0
    total_benefice = 0
    valeur_stock_total = 0
    liste_inventaire = []

    for art in articles:
        total_recu = art['quantite_initiale'] + art['quantite_ajoutee']
        restant = total_recu - art['quantite_vendue']
        
        ca_art = art['quantite_vendue'] * art['prix_vente']
        benef_art = ca_art - (art['quantite_vendue'] * art['prix_achat'])
        val_stock_art = restant * art['prix_achat']
        
        total_ca += ca_art
        total_benefice += benef_art
        valeur_stock_total += val_stock_art
        
        liste_inventaire.append({
            'nom': art['nom'], 
            'total_ajoutes': total_recu, 
            'ventes': art['quantite_vendue'], 
            'restant': restant
        })

    return jsonify({
        "finance": {
            "total_ca": total_ca, 
            "total_benefice": total_benefice, 
            "valeur_stock_total": valeur_stock_total
        },
        "inventaire": liste_inventaire
    })

@app.route('/api/creer_article', methods=['POST'])
def api_creer_article():
    """Déclare un tout nouvel article dans le catalogue de la quincaillerie."""
    nom = request.form.get('nom').strip()
    quantite = int(request.form.get('quantite'))
    prix_achat = float(request.form.get('prix_achat'))
    prix_vente = float(request.form.get('prix_vente'))
    
    conn = connexion_db()
    try:
        conn.execute("""
            INSERT INTO quincaillerie (nom, quantite_initiale, prix_achat, prix_vente)
            VALUES (?, ?, ?, ?)
        """, (nom, quantite, prix_achat, prix_vente))
        conn.commit()
        return jsonify({"statut": f"Article '{nom}' créé avec succès !"})
    except sqlite3.IntegrityError:
        return jsonify({"erreur": "Cet article existe déjà dans votre catalogue."}), 400
    finally:
        conn.close()

@app.route('/api/ajouter_stock', methods=['POST'])
def api_ajouter_stock():
    """Ajoute du stock à un produit existant lors d'un arrivage au magasin."""
    nom = request.form.get('nom').strip()
    quantite = int(request.form.get('quantite'))
    
    conn = connexion_db()
    article = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
    
    if not article:
        conn.close()
        return jsonify({"erreur": f"L'article '{nom}' n'existe pas. Créez-le d'abord à gauche."}), 400
        
    conn.execute("UPDATE quincaillerie SET quantite_ajoutee = quantite_ajoutee + ? WHERE nom = ?", (quantite, nom))
    conn.commit()
    conn.close()
    return jsonify({"statut": f"{quantite} unité(s) ajoutée(s) pour '{nom}' !"})

@app.route('/vendre_panier', methods=['POST'])
def vendre_panier():
    """Gère une liste d'articles achetés par un client, déduis les stocks et génère la facture."""
    donnees = request.get_json()
    panier = donnees.get('panier', [])
    
    conn = connexion_db()
    
    # 1. Vérification des stocks avant de valider la vente
    for item in panier:
        nom = item['nom']
        qte_demandee = int(item['quantite'])
        art = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
        if not art:
            return jsonify({"erreur": f"L'article '{nom}' n'existe pas."}), 400
        stock_actuel = art['quantite_initiale'] + art['quantite_ajoutee'] - art['quantite_vendue']
        if stock_actuel < qte_demandee:
            return jsonify({"erreur": f"Stock insuffisant pour '{nom}'. Restant : {stock_actuel}"}), 400

    id_facture = datetime.now().strftime("%Y%m%d%H%M%S")
    date_actuelle = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_general = 0
    lignes_recu = ""
    
    # 2. Validation de la vente et enregistrement dans l'historique
    for item in panier:
        nom = item['nom']
        qte_demandee = int(item['quantite'])
        art = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
        prix_unitaire = art['prix_vente']
        total_ligne = qte_demandee * prix_unitaire
        total_general += total_ligne
        
        conn.execute("UPDATE quincaillerie SET quantite_vendue = quantite_vendue + ? WHERE nom = ?", (qte_demandee, nom))
        conn.execute("""
            INSERT INTO ventes_historique (id_facture, date_vente, article_nom, quantite_vendue, prix_unitaire, total_paye)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_facture, date_actuelle, nom, qte_demandee, prix_unitaire, total_ligne))
        
        lignes_recu += f"{nom:<20} x{qte_demandee:<3} {total_ligne:>10.2f} FCFA\n"
        
    conn.commit()
    conn.close()
    
    # Construction du ticket de caisse
    recu_texte = f"""
    ==========================================
              QUINCAILLERIE DU CENTRE     
    ==========================================
    Facture N° : #{id_facture}
    Date       : {date_actuelle}
    ------------------------------------------
    Article              Qté       Total
    ------------------------------------------
{lignes_recu}------------------------------------------
    TOTAL FACTURE :       {total_general:.2f} FCFA
    ==========================================
    Merci de votre confiance !
    ==========================================
    """
    return jsonify({"statut": "Vente validée", "recu_impression": recu_texte})

if __name__ == '__main__':
    app.run(debug=True)
