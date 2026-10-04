"""
Paise columns and their legacy Decimal mirrors (ROADMAP decision A5).

Every legacy Decimal money column on Cart, CartOrder and CartOrderItem has an integer
`<name>_paise` twin. Paise is the truth and the only value pricing logic reads. The Decimal
column is still written, as a mirror, so Django admin, the order emails and the legacy
Stripe/PayPal code keep showing correct numbers.

`MoneyMirrorMixin.save()` keeps each pair equal on every save:

  * a new row written with paise only          -> the Decimal mirror is filled in
  * a new row written with Decimal only (legacy code, admin, old fixtures)
                                               -> the paise twin is filled in
  * an existing row where one side changed      -> the other side follows
  * an existing row where both sides changed    -> paise wins

The only way to make a pair drift is to bypass save() (queryset.update(), raw SQL).
`mirror_mismatches()` / `assert_mirrors()` detect that and are run after every order write
in the test suite.
"""

from decimal import Decimal

from django.db import models

from core.money import from_paise, to_paise

PAISE_SUFFIX = "_paise"


class MoneyMirrorError(AssertionError):
    """A Decimal money column and its paise twin disagree."""


def decimal_to_paise(value):
    """Legacy Decimal column value -> integer paise. None is 0; model-default floats are tolerated."""
    if value is None:
        return 0
    if isinstance(value, float):
        # Only reachable through the legacy `default=0.00` on an unsaved instance.
        value = Decimal(str(value))
    return to_paise(value)


def set_money(instance, name, paise):
    """Set `<name>_paise` and its Decimal mirror together. `name` is the legacy column name."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError(f"{name}: paise must be an int, got {type(paise).__name__}")
    if name not in instance.MONEY_FIELDS:
        raise KeyError(f"{type(instance).__name__}.{name} is not a mirrored money column")
    setattr(instance, name + PAISE_SUFFIX, paise)
    setattr(instance, name, from_paise(paise))


def mirror_mismatches(instance):
    """List of (column, decimal_value, paise_value) for every pair that disagrees."""
    problems = []
    for name in instance.MONEY_FIELDS:
        decimal_value = getattr(instance, name)
        paise_value = getattr(instance, name + PAISE_SUFFIX)
        if decimal_to_paise(decimal_value) != paise_value:
            problems.append((name, decimal_value, paise_value))
    return problems


def assert_mirrors(instance):
    """Raise MoneyMirrorError unless to_paise(decimal_column) == paise_column for every pair."""
    problems = mirror_mismatches(instance)
    if problems:
        detail = ", ".join(f"{name}={dec!r} vs {name}{PAISE_SUFFIX}={paise!r}" for name, dec, paise in problems)
        raise MoneyMirrorError(f"{type(instance).__name__}#{instance.pk} money mirror drift: {detail}")


class MoneyMirrorMixin(models.Model):
    """Keeps every `MONEY_FIELDS` Decimal column equal to its `<name>_paise` twin on save()."""

    MONEY_FIELDS = ()

    class Meta:
        abstract = True

    def _money_state(self):
        state = {}
        for name in self.MONEY_FIELDS:
            twin = name + PAISE_SUFFIX
            if name in self.__dict__ and twin in self.__dict__:
                state[name] = (decimal_to_paise(self.__dict__[name]), int(self.__dict__[twin] or 0))
        return state

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._money_loaded = instance._money_state()
        return instance

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self._money_loaded = self._money_state()

    def sync_money_mirrors(self):
        """Make every pair agree. Returns the legacy column names whose pair was changed."""
        loaded = getattr(self, "_money_loaded", None) or {}
        touched = []
        for name, (decimal_paise, paise) in self._money_state().items():
            if decimal_paise == paise:
                continue
            before = loaded.get(name)
            if before is None:
                winner = paise if paise != 0 else decimal_paise
            else:
                loaded_decimal_paise, loaded_paise = before
                if paise != loaded_paise:
                    winner = paise
                elif decimal_paise != loaded_decimal_paise:
                    winner = decimal_paise
                else:
                    winner = paise
            setattr(self, name + PAISE_SUFFIX, winner)
            setattr(self, name, from_paise(winner))
            touched.append(name)
        return touched

    def save(self, *args, **kwargs):
        touched = self.sync_money_mirrors()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            fields = set(update_fields)
            for name in self.MONEY_FIELDS:
                twin = name + PAISE_SUFFIX
                if name in fields or twin in fields or name in touched:
                    fields.update((name, twin))
            kwargs["update_fields"] = list(fields)
        super().save(*args, **kwargs)
        self._money_loaded = self._money_state()
