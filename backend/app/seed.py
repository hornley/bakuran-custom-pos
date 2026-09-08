import argparse

from .db import SEED_TIMESTAMP, initialize


def seed(c):
    c.executemany("INSERT OR IGNORE INTO suppliers VALUES (?,?,?, ?,1)", [(1,'SUP-001','Local Food Supply','')])
    c.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?, ?,1)", [(1,'CUS-001','Walk-in Customer','')])
    c.executemany("INSERT OR IGNORE INTO settings VALUES (?,?)", [('currency','PHP'),('store_name','Bakuran')])
    c.execute("INSERT OR IGNORE INTO notifications VALUES (1,'Welcome','Bakuran POS is ready.',0,?)", (SEED_TIMESTAMP,))
    c.execute("INSERT OR IGNORE INTO dining_areas VALUES (1,'MAIN','Main Dining Room')")
    for row in [(1,1,'T01','Table 1',2),(2,1,'T02','Table 2',4),(3,1,'T03','Table 3',4),(4,1,'T04','Table 4',6),(5,1,'COUNTER','Counter pickup',1)]:
        c.execute("INSERT OR IGNORE INTO dining_tables VALUES (?,?,?,?,?,?)", (*row,'available'))
    for row in [(1,'FOOD','Food'),(2,'DRINK','Drinks')]: c.execute("INSERT OR IGNORE INTO menu_categories VALUES (?,?,?,1)",row)
    items=[(1,'BRG-001',1,'House Burger','Beef burger with fries',18.0),(2,'PAS-001',1,'Garden Pasta','Seasonal vegetables and herbs',16.0),(3,'LEM-001',2,'Lemonade','Fresh house lemonade',5.0),(4,'COF-001',2,'House Coffee','Locally roasted coffee',4.0)]
    for row in items: c.execute("INSERT OR IGNORE INTO menu_items VALUES (?,?,?,?,?,?,1)",row)
    for item_id, qty in [(1,20),(2,20),(3,30),(4,30)]: c.execute("INSERT OR IGNORE INTO inventory VALUES (?,?,?, ?,0,?)",(item_id,item_id,1,qty,SEED_TIMESTAMP))
    c.executemany(
        """
        INSERT OR IGNORE INTO delivery_drivers(id, code, name, contact, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "DRV-001", "Ari Santos", "09171234567", 1, SEED_TIMESTAMP),
            (2, "DRV-002", "Ben Cruz", "09179876543", 1, SEED_TIMESTAMP),
        ],
    )
    if not c.execute("SELECT 1 FROM table_sessions WHERE id=1").fetchone():
        c.execute("INSERT INTO table_sessions VALUES (1,'SES-0001',1,'closed',?,?)",(SEED_TIMESTAMP,SEED_TIMESTAMP))
        c.execute("INSERT INTO restaurant_orders(id,order_number,session_id,status,subtotal,total,created_at,sent_at,served_at,paid_at,closed_at,customer_name,order_channel) VALUES (1,'ORD-0001',1,'closed',23,23,?,?,?,?,?,'Walk-in Customer','table')",(SEED_TIMESTAMP,SEED_TIMESTAMP,SEED_TIMESTAMP,SEED_TIMESTAMP,SEED_TIMESTAMP))
        c.execute("INSERT INTO restaurant_order_lines VALUES (1,1,3,'Lemonade',1,5,5)")
        c.execute("INSERT INTO restaurant_order_lines VALUES (2,1,1,'House Burger',1,18,18)")
        c.execute("INSERT INTO kitchen_tickets VALUES (1,'KIT-0001',1,'served','main',?,?,?,?)",(SEED_TIMESTAMP,SEED_TIMESTAMP,SEED_TIMESTAMP,SEED_TIMESTAMP))
        c.execute("INSERT INTO payments VALUES (1,'PAY-0001',1,23,'cash','paid',?)",(SEED_TIMESTAMP,))
        c.execute("INSERT INTO receipts VALUES (1,'REC-0001',1,23,?)",(SEED_TIMESTAMP,))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or reset deterministic Restaurant sample data")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all Restaurant tables first")
    initialize(reset=parser.parse_args().reset)
