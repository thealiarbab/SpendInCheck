"""
Every read and write must be confined to the signed-in user.

The interesting failure is not "someone sees another account's data on
screen" -- it is a lookup that answers about the wrong user and lets a later
call act on that answer. So these tests ask each ownership check directly.
"""

import operations


def test_investment_exists_rejects_another_users_investment(make_user):
    """investment_exists takes a user_id, so it must actually apply it."""
    owner = make_user()
    stranger = make_user()

    assert operations.add_investment(
        owner, "Reliance Industries", "Stock", "2026-01-15", "1180.00", "12", "1279.00"
    )
    investments = operations.get_all_investments(owner)
    assert len(investments) == 1
    investment_id = investments[0][0]

    # The owner can see their own holding.
    assert operations.investment_exists(owner, investment_id) is True

    # Nobody else can. Answering True here tells a caller that an investment
    # belonging to someone else is a legitimate target to act on.
    assert operations.investment_exists(stranger, investment_id) is False


def test_category_exists_rejects_another_users_category(make_user):
    """The same guarantee, on the check that already had it right."""
    owner = make_user()
    stranger = make_user()

    categories = operations.get_all_categories(owner)
    assert categories, "a new user should be seeded with starter categories"
    category_id = categories[0][0]

    assert operations.category_exists(owner, category_id) is True
    assert operations.category_exists(stranger, category_id) is False
