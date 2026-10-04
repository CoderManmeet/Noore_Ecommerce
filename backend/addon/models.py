
from django.db import models
from django.utils.html import mark_safe
from django.utils.text import slugify

from shortuuid.django_fields import ShortUUIDField

import shortuuid
import datetime




SERVICE_FEE_CHARGE_TYPE = (
    ("percentage", "Percentage"),
    ("flat_rate", "Flat Rate"),
)

AFFILIATE_COMMISSION_TYPE = (
    ("percentage", "Percentage"),
    ("flat_rate", "Flat Rate"),
)





class ConfigSettings(models.Model):
    view_more = models.CharField(default="View All", max_length=10)
    currency_sign = models.CharField(default="\u20b9", max_length=10)
    currency_abbreviation = models.CharField(default="INR", max_length=10)
    service_fee_percentage = models.IntegerField(default=5, help_text="NOTE: Numbers added here are in percentage (%)ve.g 4%")
    service_fee_flat_rate = models.DecimalField(default=0.7, max_digits=12, decimal_places=2 ,help_text="NOTE: Add the amount you want to charge as service fee e.g $2.30")
    service_fee_charge_type = models.CharField(default="percentage", max_length=30, choices=SERVICE_FEE_CHARGE_TYPE)
    enforce_2fa = models.BooleanField(default=True)
    activate_affiliate_system = models.BooleanField(default=True)
    send_email_notifications = models.BooleanField(default=False)

    # --- pricing (Phase G1). All amounts are integer paise. --------------------------------------
    shipping_flat_paise = models.BigIntegerField(default=7900, help_text="Flat shipping charged once per order, in paise (Rs 79 = 7900).")
    free_shipping_threshold_paise = models.BigIntegerField(default=99900, help_text="Shipping is free when the subtotal after discount is at least this many paise (Rs 999 = 99900).")
    tax_rate_bps = models.PositiveIntegerField(default=0, help_text="Tax rate in basis points (18% = 1800). Prices are tax-inclusive: tax is carved out of the price, never added on top. 0 while the business is not GST-registered.")
    
    class Meta:
        verbose_name = ("Settings")
        verbose_name_plural = ("Settings")


    
    
class Tax(models.Model):
    country = models.CharField(max_length=500)
    rate = models.IntegerField(default=5, help_text="Numbers added here are in percentage (5 = 5%)")
    active = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Tax"

    def __str__(self):
        return f"{self.country}"
    

        
