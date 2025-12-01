"""
Script de migration SQLite → PostgreSQL
NBCM v3.0

Ce script migre toutes les données de SQLite vers PostgreSQL
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect
import sqlite3
from datetime import datetime

# Configuration
SQLITE_DB = os.environ.get('SQLITE_DB', 'data/db/nbcm.db')
POSTGRES_URL = os.environ.get('DATABASE_URL', 'postgresql://nbcm:nbcm2025@localhost:5432/nbcm')

def migrate():
    """Migre les données SQLite vers PostgreSQL"""
    
    print("=" * 60)
    print("🔄 MIGRATION SQLite → PostgreSQL")
    print("=" * 60)
    print(f"\n📁 Source SQLite: {SQLITE_DB}")
    print(f"🐘 Destination PostgreSQL: {POSTGRES_URL.split('@')[1] if '@' in POSTGRES_URL else POSTGRES_URL}")
    print()
    
    # Vérifier que SQLite existe
    if not os.path.exists(SQLITE_DB):
        print(f"❌ Erreur: Fichier SQLite introuvable: {SQLITE_DB}")
        sys.exit(1)
    
    # Connexion SQLite
    try:
        sqlite_conn = sqlite3.connect(SQLITE_DB)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        print("✅ Connexion SQLite OK")
    except Exception as e:
        print(f"❌ Erreur connexion SQLite: {e}")
        sys.exit(1)
    
    # Connexion PostgreSQL
    try:
        pg_engine = create_engine(POSTGRES_URL)
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.scalar()
            print(f"✅ Connexion PostgreSQL OK")
            print(f"   Version: {version.split(',')[0]}")
    except Exception as e:
        print(f"❌ Erreur connexion PostgreSQL: {e}")
        print("\n💡 Vérifiez:")
        print("   1. PostgreSQL est démarré: docker-compose ps")
        print("   2. DATABASE_URL est correct dans .env")
        print("   3. Les credentials sont bons")
        sys.exit(1)
    
    # Récupérer liste des tables SQLite
    sqlite_cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    
    sqlite_tables = [row[0] for row in sqlite_cursor.fetchall()]
    print(f"\n📊 Tables trouvées dans SQLite: {len(sqlite_tables)}")
    for table in sqlite_tables:
        print(f"   • {table}")
    
    # Vérifier tables PostgreSQL
    inspector = inspect(pg_engine)
    pg_tables = inspector.get_table_names()
    print(f"\n📊 Tables disponibles dans PostgreSQL: {len(pg_tables)}")
    for table in pg_tables:
        print(f"   • {table}")
    
    if not pg_tables:
        print("\n⚠️  ATTENTION: PostgreSQL n'a aucune table!")
        print("   Avez-vous lancé les migrations Flask-Migrate ?")
        print("   Commande: flask db upgrade")
        response = input("\nContinuer quand même ? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Migration table par table
    print("\n" + "=" * 60)
    print("📦 MIGRATION DES DONNÉES")
    print("=" * 60)
    
    total_migrated = 0
    errors = []
    
    for table in sqlite_tables:
        if table not in pg_tables:
            print(f"\n⏭️  {table}: Table inexistante dans PostgreSQL, skip")
            continue
        
        print(f"\n📋 Migration: {table}")
        
        # Compter lignes SQLite
        sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = sqlite_cursor.fetchone()[0]
        print(f"   SQLite: {count:,} lignes")
        
        if count == 0:
            print(f"   ⏭️  Table vide, skip")
            continue
        
        # Récupérer structure
        sqlite_cursor.execute(f"PRAGMA table_info({table})")
        columns_info = sqlite_cursor.fetchall()
        columns = [col[1] for col in columns_info]
        
        # Récupérer toutes les données
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        
        # Insérer dans PostgreSQL
        migrated = 0
        with pg_engine.connect() as conn:
            for row in rows:
                # Construire dictionnaire
                row_dict = dict(zip(columns, row))
                
                # Construire requête INSERT
                cols = ', '.join(columns)
                placeholders = ', '.join([f':{col}' for col in columns])
                insert_query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
                
                try:
                    conn.execute(text(insert_query), row_dict)
                    migrated += 1
                except Exception as e:
                    error_msg = f"{table}: {str(e)[:100]}"
                    errors.append(error_msg)
            
            conn.commit()
        
        # Vérifier
        with pg_engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            pg_count = result.scalar()
            print(f"   PostgreSQL: {pg_count:,} lignes")
            
            if pg_count == count:
                print(f"   ✅ Migration OK ({migrated:,} lignes)")
                total_migrated += migrated
            else:
                diff = count - pg_count
                print(f"   ⚠️  Attention: {diff:,} lignes manquantes")
                errors.append(f"{table}: {diff} lignes manquantes")
    
    # Résumé
    print("\n" + "=" * 60)
    print("📊 RÉSUMÉ MIGRATION")
    print("=" * 60)
    print(f"\n✅ Total lignes migrées: {total_migrated:,}")
    
    if errors:
        print(f"\n⚠️  {len(errors)} erreur(s) détectée(s):")
        for error in errors[:10]:  # Max 10 premières erreurs
            print(f"   • {error}")
        if len(errors) > 10:
            print(f"   ... et {len(errors) - 10} autres erreurs")
    else:
        print("\n🎉 Aucune erreur détectée!")
    
    # Statistiques finales
    print("\n" + "=" * 60)
    print("📈 VÉRIFICATION FINALE")
    print("=" * 60)
    
    with pg_engine.connect() as conn:
        for table in pg_tables:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"   {table}: {count:,} lignes")
    
    # Fermeture
    sqlite_conn.close()
    
    print("\n" + "=" * 60)
    print("✅ MIGRATION TERMINÉE")
    print("=" * 60)
    print("\n🔍 Pour vérifier manuellement:")
    print("   docker exec -it nbcm-postgres psql -U nbcm -d nbcm")
    print("\n🚀 Prochaines étapes:")
    print("   1. Tester l'application: docker-compose up -d nbcm")
    print("   2. Vérifier dashboard: http://localhost:5000")
    print("   3. Créer premier backup: Admin > Backup & Restore")
    print()

if __name__ == '__main__':
    try:
        migrate()
    except KeyboardInterrupt:
        print("\n\n❌ Migration interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
