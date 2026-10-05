# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_value_from_production(self, quantity):
        self.ensure_one()
        if self.production_id and self.production_id.bom_id and self.production_id.bom_id.butcher_test:
            butcher_line = self.production_id.butcher_line_ids.filtered(lambda l: l.product_id == self.product_id)
            if butcher_line:
                line = butcher_line[0]
                # If quantity matches actual produced quantity, use exact reconciled total_cost
                if self.uom_id and self.uom_id.compare(quantity, line.actual_qty) == 0:
                    val = line.total_cost
                else:
                    val = self.company_currency_id.round(quantity * line.cost_per_unit)
                return {
                    'value': val,
                    'quantity': quantity,
                    'description': self.env._(
                        '%(value)s for %(quantity)s %(unit)s from %(production)s (Butcher Test)',
                        value=self.company_currency_id.format(val),
                        quantity=quantity,
                        unit=self.product_id.uom_id.name,
                        production=self.production_id.display_name
                    ),
                }
        return super()._get_value_from_production(quantity)
