import bcrypt

def hash(password: str) -> str:
    """
    Hashes a plain-text password securely using a native, cryptographically random salt.
    Optimized to run safely inside asynchronous multi-threaded environments.
    """
    # 1. Convert plain-text string to raw bytes
    password_bytes = password.encode('utf-8')
    
    # 2. Generate a secure random salt (defaults to 12 work rounds)
    salt = bcrypt.gensalt()
    
    # 3. Hash the bytes and decode back to a clean string format for PostgreSQL
    hashed_password_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_password_bytes.decode('utf-8')


def verify(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against a hashed string stored in the database.
    """
    try:
        # Convert both strings into raw byte buffers for cryptographic comparison
        plain_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        
        # Run standard constant-time comparison to prevent timing attacks
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        # Gracefully catch malformed or broken hashes instead of crashing the server thread
        return False
