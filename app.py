from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

def connexion_db():
    conn = sqlite3.connect("quincaillerie_reseau.db")
    conn.row_factory = sqlite3.Row
    return conn

# Préparation automatique des tables de la quincaillerie
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
    try:
        conn.execute("INSERT INTO quincaillerie (nom, quantite_initiale, prix_achat, prix_vente) VALUES (?, ?, ?, ?)", ("Sac de Ciment 50kg", 100, 4500, 5500))
        conn.execute("INSERT INTO quincaillerie (nom, quantite_initiale, prix_achat, prix_vente) VALUES (?, ?, ?, ?)", ("Boite de Vis à bois", 50, 1200, 2000))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

@app.route('/')
def tableau_de_bord():
    return render_template('index.html')

@app.route('/api/donnies_patron')
def api_donnies_patron():
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

@app.route('/vendre_panier', methods=['POST'])
def vendre_panier():
    donnees = request.get_json()
    if not donnees or 'panier' not in donnees:
        return jsonify({"erreur": "Données du panier invalides"}), 400
        
    panier = donnees['panier']
    if not panier:
        return jsonify({"erreur": "Le panier est vide"}), 400
        
    conn = connexion_db()
    
    # Vérification des stocks
    for item in panier:
        nom = item['nom']
        qte_demandee = int(item['quantite'])
        art = conn.execute("SELECT * FROM quincaillerie WHERE nom = ?", (nom,)).fetchone()
        if not art:
            return jsonify({"erreur": f"L'article '{nom}' n'existe pas."}), 400
        stock_actuel = art['quantite_initiale'] + art['quantite_ajoutee'] - art['quantite_vendue']
        if stock_actuel < qte_demandee:
            return jsonify({"erreur": f"Stock insuffisant pour '{nom}'. Restant : {stock_actuel}"}), 400

    # Validation et calcul du reçu
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
        conn.execute("""
            INSERT INTO ventes_historique (id_facture, date_vente, article_nom, quantite_vendue, prix_unitaire, total_paye)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_facture, date_actuelle, nom, qte_demandee, prix_unitaire, total_ligne))
        
        lignes_recu += f"{nom:<20} x{qte_demandee:<3} {total_ligne:>10.2f} FCFA\n"
        
    conn.commit()
    conn.close()
    
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