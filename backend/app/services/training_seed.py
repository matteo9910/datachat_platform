"""
Training Seed per HybridVannaService
Esempi per schema: fact_orders, dim_products, inventory_snapshot
"""

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# TRAINING DATA - Schema logistic_poc (Supabase)
# Tables: fact_orders, dim_products, inventory_snapshot
# ============================================================================

TRAINING_DATA: List[Tuple[str, str]] = [
    # --- VENDITE BASE ---
    ("Mostra le vendite totali",
     "SELECT SUM(sales) as total_sales FROM fact_orders"),
    
    ("Vendite totali",
     "SELECT SUM(sales) as total_sales FROM fact_orders"),
    
    ("Quanti ordini ci sono in totale?",
     "SELECT COUNT(DISTINCT order_id) as total_orders FROM fact_orders"),
    
    ("Quante righe ci sono nella tabella ordini?",
     "SELECT COUNT(*) as row_count FROM fact_orders"),
    
    ("Qual e il valore medio degli ordini?",
     "SELECT AVG(sales) as avg_order_value FROM fact_orders"),

    # --- VENDITE PER CATEGORIA ---
    ("Vendite per categoria",
     """SELECT p.category_name, SUM(f.sales) as total_sales 
        FROM fact_orders f 
        JOIN dim_products p ON f.product_id = p.product_id 
        GROUP BY p.category_name ORDER BY total_sales DESC"""),
    
    ("Qual e il fatturato totale per categoria di prodotto?",
     """SELECT p.category_name, SUM(f.sales) as total_sales 
        FROM fact_orders f 
        JOIN dim_products p ON f.product_id = p.product_id 
        GROUP BY p.category_name ORDER BY total_sales DESC"""),
    
    ("Top 10 prodotti per vendite",
     """SELECT p.product_name, SUM(f.sales) as total_sales 
        FROM fact_orders f 
        JOIN dim_products p ON f.product_id = p.product_id 
        GROUP BY p.product_name ORDER BY total_sales DESC LIMIT 10"""),

    # --- ANALISI TEMPORALE ---
    ("Vendite per mese",
     """SELECT DATE_TRUNC('month', order_date) as month, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY DATE_TRUNC('month', order_date) ORDER BY month"""),
    
    ("Andamento delle vendite nel tempo",
     """SELECT DATE_TRUNC('month', order_date) as month, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY DATE_TRUNC('month', order_date) ORDER BY month"""),
    
    ("Mostrami l'andamento delle vendite nel tempo",
     """SELECT DATE_TRUNC('month', order_date) as month, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY DATE_TRUNC('month', order_date) ORDER BY month"""),
    
    ("Vendite per anno",
     """SELECT EXTRACT(YEAR FROM order_date) as year, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY EXTRACT(YEAR FROM order_date) ORDER BY year"""),
    
    ("Vendite per giorno della settimana",
     """SELECT EXTRACT(DOW FROM order_date) as day_of_week, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY EXTRACT(DOW FROM order_date) ORDER BY day_of_week"""),

    # --- ANALISI CLIENTE ---
    ("Vendite per segmento cliente",
     """SELECT customer_segment, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY customer_segment ORDER BY total_sales DESC"""),
    
    ("Vendite per citta",
     """SELECT customer_city, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY customer_city ORDER BY total_sales DESC LIMIT 20"""),
    
    ("Top 10 citta per fatturato",
     """SELECT customer_city, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY customer_city ORDER BY total_sales DESC LIMIT 10"""),

    # --- ANALISI SPEDIZIONI ---
    ("Ordini per modalita di spedizione",
     """SELECT shipping_mode, COUNT(DISTINCT order_id) as order_count, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY shipping_mode ORDER BY total_sales DESC"""),
    
    ("Stato delle consegne",
     """SELECT delivery_status, COUNT(*) as count, SUM(sales) as total_sales 
        FROM fact_orders 
        GROUP BY delivery_status ORDER BY count DESC"""),

    # --- INVENTARIO ---
    ("Mostra lo stock attuale per prodotto",
     """SELECT p.product_name, i.current_stock_qty, i.reorder_point, i.warehouse_location
        FROM inventory_snapshot i 
        JOIN dim_products p ON i.product_id = p.product_id 
        ORDER BY i.current_stock_qty DESC"""),
    
    ("Prodotti sotto il punto di riordino",
     """SELECT p.product_name, i.current_stock_qty, i.reorder_point 
        FROM inventory_snapshot i 
        JOIN dim_products p ON i.product_id = p.product_id 
        WHERE i.current_stock_qty < i.reorder_point 
        ORDER BY (i.reorder_point - i.current_stock_qty) DESC"""),
    
    ("Stock per magazzino",
     """SELECT warehouse_location, SUM(current_stock_qty) as total_stock 
        FROM inventory_snapshot 
        GROUP BY warehouse_location ORDER BY total_stock DESC"""),

    # --- JOIN COMPLESSI ---
    ("Vendite e stock per categoria",
     """SELECT p.category_name, 
               SUM(f.sales) as total_sales,
               SUM(i.current_stock_qty) as total_stock
        FROM dim_products p
        LEFT JOIN fact_orders f ON p.product_id = f.product_id
        LEFT JOIN inventory_snapshot i ON p.product_id = i.product_id
        GROUP BY p.category_name ORDER BY total_sales DESC"""),
    
    # --- QUANTITA ---
    ("Quantita totale venduta",
     "SELECT SUM(order_item_quantity) as total_quantity FROM fact_orders"),
    
    ("Quantita venduta per prodotto",
     """SELECT p.product_name, SUM(f.order_item_quantity) as total_quantity 
        FROM fact_orders f 
        JOIN dim_products p ON f.product_id = p.product_id 
        GROUP BY p.product_name ORDER BY total_quantity DESC LIMIT 20"""),
]

# ============================================================================
# DOCUMENTAZIONE SCHEMA
# ============================================================================

DOCUMENTATION: List[str] = [
    """
    ## Schema Database Logistic POC
    
    ### fact_orders (Tabella dei Fatti - Ordini)
    Contiene tutti gli ordini e le vendite.
    - order_id: ID univoco dell ordine
    - order_item_id: ID della riga ordine
    - product_id: FK a dim_products
    - order_date: Data dell ordine (timestamp)
    - sales: Valore vendita in euro
    - order_item_quantity: Quantita ordinata
    - delivery_status: Stato consegna (es. Delivered, Pending)
    - shipping_mode: Modalita spedizione (es. Standard, Express)
    - customer_city: Citta del cliente
    - customer_segment: Segmento cliente (es. Consumer, Corporate)
    
    ### dim_products (Dimensione Prodotti)
    Anagrafica prodotti.
    - product_id: PK
    - product_name: Nome prodotto
    - category_name: Categoria
    - product_price: Prezzo unitario
    - product_image: URL immagine
    
    ### inventory_snapshot (Snapshot Inventario)
    Livelli di stock attuali.
    - inventory_id: PK
    - product_id: FK a dim_products
    - warehouse_location: Ubicazione magazzino
    - current_stock_qty: Quantita in stock
    - reorder_point: Soglia riordino
    
    ### Relazioni
    - fact_orders.product_id -> dim_products.product_id
    - inventory_snapshot.product_id -> dim_products.product_id
    """,
    
    """
    ## Metriche Comuni
    
    - Vendite totali: SUM(sales) da fact_orders
    - Numero ordini: COUNT(DISTINCT order_id) da fact_orders
    - Quantita venduta: SUM(order_item_quantity) da fact_orders
    - Valore medio ordine: AVG(sales) da fact_orders
    - Stock totale: SUM(current_stock_qty) da inventory_snapshot
    
    ## Dimensioni Analisi
    - Tempo: order_date (DATE_TRUNC per aggregazioni)
    - Prodotto: JOIN con dim_products per category_name, product_name
    - Cliente: customer_segment, customer_city da fact_orders
    - Spedizione: shipping_mode, delivery_status da fact_orders
    - Magazzino: warehouse_location da inventory_snapshot
    """
]

def get_training_examples() -> List[Tuple[str, str]]:
    """Ritorna tutti gli esempi di training"""
    return TRAINING_DATA

def get_documentation() -> List[str]:
    """Ritorna la documentazione dello schema"""
    return DOCUMENTATION

def auto_generate_examples_for_tables(tables: List[str]) -> List[Tuple[str, str]]:
    """Genera esempi base automaticamente per nuove tabelle"""
    examples = []
    for table in tables:
        examples.append((f"Mostra tutti i record di {table}", f"SELECT * FROM {table} LIMIT 100"))
        examples.append((f"Conta i record in {table}", f"SELECT COUNT(*) as count FROM {table}"))
    return examples
