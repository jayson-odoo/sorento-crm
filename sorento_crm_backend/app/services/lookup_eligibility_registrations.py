"""Declare bindable (model, column) pairs here. Each must have a friendly label.

Add new entries by importing the model and calling register_lookup_eligible.
Admins cannot edit eligibility; ask a developer.
"""
from app.services.lookup_eligibility import register_lookup_eligible

# Example (kept commented until a real model adopts it):
# from app.models.order import Order
# register_lookup_eligible(
#     model=Order, column="priority",
#     table_label="Order", column_label="Priority",
# )
