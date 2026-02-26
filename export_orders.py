import sqlite3

# Connect to the database
conn = sqlite3.connect("orders.db")
cursor = conn.cursor()

# Fetch all orders
cursor.execute("SELECT * FROM orders")
orders = cursor.fetchall()

# Open a text file to write orders
with open("all_orders.txt", "w", encoding="utf-8") as f:
    if not orders:
        f.write("No orders found.\n")
    else:
        for idx, order in enumerate(orders, 1):
            user_id, name, link, quantity, order_number = order
            f.write(f"Order #{idx}\n")
            f.write(f"User ID      : {user_id}\n")
            f.write(f"Name         : {name}\n")
            f.write(f"Product Link : {link}\n")
            f.write(f"Quantity     : {quantity}\n")
            f.write(f"Order Number : {order_number}\n")
            f.write("-" * 50 + "\n")

print("All orders exported to all_orders.txt successfully!")

conn.close()
