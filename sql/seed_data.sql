-- Insert sample users
INSERT INTO users (name, email) VALUES 
    ('John Doe', 'john@example.com'),
    ('Jane Smith', 'jane@company.com'),
    ('Bob Wilson', 'bob@test.org'),
    ('Alice Brown', 'alice@demo.com'),
    ('Charlie Davis', 'charlie@sample.com');

-- Insert sample products
INSERT INTO products (name, price, category) VALUES 
    ('Laptop Pro', 1299.99, 'Electronics'),
    ('Wireless Mouse', 29.99, 'Electronics'),
    ('Office Chair', 199.99, 'Furniture'),
    ('Standing Desk', 449.99, 'Furniture'),
    ('USB-C Hub', 79.99, 'Electronics'),
    ('Monitor 4K', 399.99, 'Electronics'),
    ('Keyboard Mechanical', 149.99, 'Electronics'),
    ('Webcam HD', 89.99, 'Electronics');

-- Insert sample orders
INSERT INTO orders (user_id, product_id, quantity, total_amount, status) VALUES 
    (1, 1, 1, 1299.99, 'completed'),
    (1, 2, 2, 59.98, 'completed'),
    (2, 3, 1, 199.99, 'shipped'),
    (2, 4, 1, 449.99, 'processing'),
    (3, 5, 3, 239.97, 'completed'),
    (3, 6, 1, 399.99, 'shipped'),
    (4, 7, 2, 299.98, 'processing'),
    (5, 8, 1, 89.99, 'completed'),
    (1, 3, 1, 199.99, 'completed'),
    (2, 1, 1, 1299.99, 'shipped');