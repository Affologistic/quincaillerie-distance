from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

def connexion_db():
    conn = sqlite3.connect("quincaillerie_reseau.db")
    conn.row_factory = sqlite3.Row
    return conn

# Initialisation de la base de données
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
    
    # CHARGEMENT FORCÉ DES ARTICLES DU TOGO
    articles_togo = [
        ("Sac de Ciment Cimtogo 50kg", 100, 3850.0, 4100.0),
        ("Fer a beton 12mm (Barre)", 150, 4000.0, 4500.0),
        ("Fer a beton 10mm (Barre)", 200, 3100.0, 3600.0),
        ("Fer a beton 8mm (Barre)", 250, 2000.0, 2400.0),
        ("Rouleau Fil de ligature", 30, 9000.0, 11000.0),
        ("Tole ondulee (Paquet)", 15, 45000.0, 52000.0),
        ("Pot Peinture Blanche 20L", 20, 14000.0, 18500.0),
        ("Paquet de Pointes 80mm", 40, 4500.0, 5500.0),
        ("Brouette de chantier", 10, 18000.0, 22500.0),
        ("Pelle ronde avec manche", 25, 2500.0, 3500.0)
    ]
    try:
        for art in articles_togo:
            conn.execute("INSERT OR IGNORE INTO quincaillerie (nom, quantite_initiale, prix_achat, prix_vente) VALUES (?, ?, ?, ?)", art)
        conn.commit()
    except sqlite3.OperationalError:
        pass

@app.route('/')
def tableau_de_bord():
    return render_template('index.html')

@app.route('/api/donnees_patron')
def api_donnees_patron():
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
            'nom': art['nom'], 'total_ajoutes': total_recu, 'ventes': art['quantite_vendue'], 'restant': restant
        })

    return jsonify({
        "finance": {"total_ca": total_ca, "total_benefice": total_benefice, "valeur_stock_total": valeur_stock_total},
        "inventaire": liste_inventaire
    })

@app.route('/api/creer_article', methods=['POST'])
def api_creer_article():
    """Déclare un tout nouvel article dans la base de données."""
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
        return jsonify({"statut": "Succes"})
    except sqlite3.IntegrityError:
        return jsonify({"erreur": "Existe deja"}), 400
    finally:
        conn.close()

@app.route('/api/ajouter_stock', methods=['POST'])
def api_ajouter_stock():
    """Ajoute du stock à un produit existant lors d'un arrivage."""
    nom = request.form.get('nom').strip()
    quantite = int(request.form.get('quantite'))
    
    conn = connexion_db()
    article = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
    
    if not article:
        conn.close()
        return jsonify({"erreur": "Introuvable"}), 400
        
    conn.execute("UPDATE quincaillerie SET quantite_ajoutee = quantite_ajoutee + ? WHERE nom = ?", (quantite, nom))
    conn.commit()
    conn.close()
    return jsonify({"statut": "Succes"})

@app.route('/vendre_panier', methods=['POST'])
def vendre_panier():
    donnees = request.get_json()
    panier = donnees.get('panier', [])
    conn = connexion_db()
    
    for item in panier:
        nom = item['nom']
        qte_demandee = int(item['quantite'])
        art = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
        if not art:
            return jsonify({"erreur": f"L'article '{nom}' n'existe pas."}), 400
        stock_actuel = art['quantite_initiale'] + art['quantite_ajoutee'] - art['quantite_vendue']
        if stock_actuel < qte_demandee:
            return jsonify({"erreur": f"Stock insuffisant pour '{nom}'."}), 400

    id_facture = datetime.now().strftime("%Y%m%d%H%M%S")
    date_actuelle = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_general = 0
    lignes_recu = ""
    
    for item in panier:
        nom = item['nom']
        qte_demandee = int(item['quantite'])
        art = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
        prix_unitaire = art['prix_vente']
        total_ligne = qte_demandee * prix_unitaire
        total_general += total_ligne
        
        conn.execute("UPDATE quincaillerie SET quantite_vendue = quantite_vendue + ? WHERE nom = ?", (qte_demandee, nom))
        conn.execute("INSERT INTO ventes_historique (id_facture, date_vente, article_nom, quantite_vendue, prix_unitaire, total_paye) VALUES (?, ?, ?, ?, ?, ?)", (id_facture, date_actuelle, nom, qte_demandee, prix_unitaire, total_ligne))
        lignes_recu += f"{nom:<25} x{qte_demandee:<3} {total_ligne:>10.2f} FCFA\n"
        
    conn.commit()
    conn.close()
    
    recu_texte = f"===========================================\n          QUINCAILLERIE DU CENTRE     \n===========================================\nFacture N° : #{id_facture}\nDate       : {date_actuelle}\n-------------------------------------------\nArticle               Qté       Total\n-------------------------------------------\n{lignes_recu}-------------------------------------------\nTOTAL FACTURE :       {total_general:.2f} FCFA\n===========================================\nMerci de votre confiance !\n==========================================="
    return jsonify({"statut": "Vente validee", "recu_impression": recu_texte})

if __name__ == '__main__':
    app.run(debug=True)
