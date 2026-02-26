import sqlite3

# Connect to the database
conn = sqlite3.connect("orders.db")
cursor = conn.cursor()

# Fetch all orders
cursor.execute("SELECT * FROM orders")
orders = cursor.fetchall()

if not orders:
    print("No orders found.")
else:
    for order in orders:
        user_id, name, link, quantity, order_number = order
        print(f"User ID: {user_id}")
        print(f"Name: {name}")
        print(f"Link: {link}")
        print(f"Quantity: {quantity}")
        print(f"Order Number: {order_number}")
        print("-" * 40)

conn.close()
