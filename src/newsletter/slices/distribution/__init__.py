"""Distribution slice — SMTP newsletter delivery.

Replaces the admin send route's 501 placeholder with a real Gmail-SMTP
backed send. The state-machine guard (``status == 'approved'``) is
enforced here, not just in the UI route — there is no ``--force`` flag.
"""
