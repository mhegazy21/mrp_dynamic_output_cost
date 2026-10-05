# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
    )
    is_butcher_test = fields.Boolean(
        related='bom_id.butcher_test',
        string='Is Butcher Test',
        store=True,
    )
    butcher_total_production_cost = fields.Monetary(
        string='Total Actual Production Cost',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    butcher_total_relative_qty = fields.Float(
        string='Total Relative Quantity',
        digits='Product Unit of Measure',
        readonly=True,
        copy=False,
    )
    butcher_relative_price = fields.Monetary(
        string='Relative Price',
        currency_field='currency_id',
        readonly=True,
        copy=False,
    )
    butcher_line_ids = fields.One2many(
        'mrp.production.butcher.line',
        'production_id',
        string='Butcher Test Costing Lines',
        copy=False,
    )
    butcher_is_frozen = fields.Boolean(
        string='Butcher Cost Frozen',
        default=False,
        copy=False,
    )

    def action_confirm(self):
        res = super().action_confirm()
        for production in self:
            if production.is_butcher_test:
                production._compute_butcher_costing()
        return res

    @api.onchange('qty_producing', 'bom_id')
    def _onchange_butcher_outputs(self):
        if self.is_butcher_test and self.state not in ('done', 'cancel'):
            self._compute_butcher_costing()

    def action_recompute_butcher_cost(self):
        self.ensure_one()
        if self.state in ('done', 'cancel') or self.butcher_is_frozen:
            raise UserError(_("Costing is frozen once the Manufacturing Order is Done."))
        self._compute_butcher_costing()
        return True

    def _compute_butcher_costing(self, total_actual_cost=None):
        self.ensure_one()
        if not self.bom_id or not self.bom_id.butcher_test:
            return

        if self.state == 'done' and self.butcher_is_frozen:
            return

        currency = self.currency_id or self.company_id.currency_id

        # 1. Calculate Total Actual Production Cost
        if total_actual_cost is None:
            component_cost = 0.0
            for move in self.move_raw_ids:
                if move.state == 'cancel':
                    continue
                if move.state == 'done' and move.value:
                    component_cost += abs(move.value)
                else:
                    qty = move.quantity or move.product_uom_qty
                    price_unit = move.price_unit or move.product_id.standard_price
                    component_cost += qty * price_unit

            work_center_cost = sum(wo._cal_cost() for wo in self.workorder_ids)
            total_actual_cost = component_cost + work_center_cost

        total_actual_cost = currency.round(total_actual_cost)

        # 2. Gather outputs data
        outputs_data = []
        bom_importance = {
            line.product_id.id: line.relative_importance
            for line in self.bom_id.butcher_output_ids
        }

        # Main product output
        main_product = self.product_id
        main_qty = self.qty_producing or self.product_qty
        main_importance = bom_importance.get(main_product.id, 0.0)
        outputs_data.append({
            'product_id': main_product.id,
            'is_main_product': True,
            'relative_importance': main_importance,
            'actual_qty': main_qty,
        })

        # By-product outputs
        for bp_move in self.move_byproduct_ids.filtered(lambda m: m.state != 'cancel'):
            bp_prod = bp_move.product_id
            bp_qty = bp_move.quantity or bp_move.product_uom_qty
            bp_importance = bom_importance.get(bp_prod.id, 0.0)
            outputs_data.append({
                'product_id': bp_prod.id,
                'is_main_product': False,
                'relative_importance': bp_importance,
                'actual_qty': bp_qty,
            })

        # 3. Calculations
        total_actual_qty = sum(item['actual_qty'] for item in outputs_data)
        total_relative_qty = 0.0

        for item in outputs_data:
            # Relative Quantity = Relative Importance % × Actual Produced Quantity
            rel_qty = (item['relative_importance'] / 100.0) * item['actual_qty']
            item['relative_qty'] = rel_qty
            item['actual_qty_share'] = (item['actual_qty'] / total_actual_qty * 100.0) if total_actual_qty else 0.0
            total_relative_qty += rel_qty

        # Relative Price = Total Actual Production Cost ÷ Total Relative Quantity
        relative_price = (total_actual_cost / total_relative_qty) if total_relative_qty else 0.0

        # 4. Total Output Cost & Rounding Distribution
        sum_rounded_cost = 0.0
        for item in outputs_data:
            item['relative_price'] = relative_price
            raw_cost = item['relative_qty'] * relative_price
            rounded_cost = currency.round(raw_cost)
            item['total_cost'] = rounded_cost
            sum_rounded_cost += rounded_cost

        # Distribute rounding difference proportionally by Relative Importance %
        rounding_diff = currency.round(total_actual_cost - sum_rounded_cost)
        total_importance = sum(item['relative_importance'] for item in outputs_data)

        if not currency.is_zero(rounding_diff) and total_importance > 0:
            distributed = 0.0
            for item in outputs_data:
                adj = currency.round(rounding_diff * (item['relative_importance'] / total_importance))
                item['total_cost'] += adj
                distributed += adj
            residual = currency.round(rounding_diff - distributed)
            if not currency.is_zero(residual):
                max_item = max(outputs_data, key=lambda x: x['relative_importance'])
                max_item['total_cost'] += residual

        # Cost per Unit = Total Output Cost ÷ Actual Produced Quantity
        for item in outputs_data:
            if item['actual_qty']:
                item['cost_per_unit'] = item['total_cost'] / item['actual_qty']
            else:
                item['cost_per_unit'] = 0.0

        # Update production order
        self.butcher_total_production_cost = total_actual_cost
        self.butcher_total_relative_qty = total_relative_qty
        self.butcher_relative_price = relative_price

        # Update butcher_line_ids
        line_commands = [(5, 0, 0)]
        for item in outputs_data:
            line_commands.append((0, 0, {
                'product_id': item['product_id'],
                'is_main_product': item['is_main_product'],
                'relative_importance': item['relative_importance'],
                'actual_qty': item['actual_qty'],
                'actual_qty_share': item['actual_qty_share'],
                'relative_qty': item['relative_qty'],
                'relative_price': item['relative_price'],
                'total_cost': item['total_cost'],
                'cost_per_unit': item['cost_per_unit'],
            }))
        self.butcher_line_ids = line_commands

    def _cal_price(self, consumed_moves):
        """Override to implement root-level replacement of standard valuation for Butcher Test BoMs."""
        if not self.bom_id or not self.bom_id.butcher_test:
            return super()._cal_price(consumed_moves)

        # 7. Total Actual Production Cost: Components + Operations
        component_cost = abs(sum(consumed_moves.mapped('value')))
        work_center_cost = sum(wo._cal_cost() for wo in self.workorder_ids)
        total_actual_cost = component_cost + work_center_cost

        # Recalculate Butcher Test Costing at the exact moment of Done
        self._compute_butcher_costing(total_actual_cost=total_actual_cost)

        # Set price_unit directly on finished move
        finished_moves = self.move_finished_ids.filtered(
            lambda m: m.product_id == self.product_id and m.state not in ('done', 'cancel')
            and m.uom_id.compare(m.quantity, 0) > 0
        )
        main_line = self.butcher_line_ids.filtered(lambda l: l.product_id == self.product_id)
        if finished_moves and main_line:
            finished_moves.price_unit = main_line[0].cost_per_unit

        # Set price_unit directly on byproduct moves
        byproduct_moves = self.move_byproduct_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.uom_id.compare(m.quantity, 0) > 0
        )
        for bp in byproduct_moves:
            bp_line = self.butcher_line_ids.filtered(lambda l: l.product_id == bp.product_id)
            if bp_line:
                bp.price_unit = bp_line[0].cost_per_unit

        # Freeze costing after Done
        self.butcher_is_frozen = True
        return True


class MrpProductionButcherLine(models.Model):
    _name = 'mrp.production.butcher.line'
    _description = 'Manufacturing Order Butcher Test Costing Line'
    _order = 'production_id, is_main_product desc, id'

    production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one('product.product', string='Product', required=True)
    is_main_product = fields.Boolean(string='Main Product', default=False)
    relative_importance = fields.Float(
        string='Relative Importance (%)',
        digits=(16, 4),
        help="Value configured on the BoM",
    )
    actual_qty = fields.Float(
        string='Actual Produced Quantity',
        digits='Product Unit of Measure',
    )
    actual_qty_share = fields.Float(
        string='Actual Qty Share %',
        digits=(16, 2),
        help="Actual produced quantity of this output / total actual produced quantity of all outputs",
    )
    relative_qty = fields.Float(
        string='Relative Quantity',
        digits=(16, 4),
        help="Relative Importance % × Actual Produced Quantity",
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='production_id.currency_id',
        string='Currency',
        readonly=True,
    )
    relative_price = fields.Monetary(
        string='Relative Price / Unit',
        currency_field='currency_id',
        help="Calculated common relative price",
    )
    total_cost = fields.Monetary(
        string='Total Output Cost',
        currency_field='currency_id',
        help="Total cost allocated to the output",
    )
    cost_per_unit = fields.Float(
        string='Cost per Unit',
        digits='Product Price',
        help="Final unit cost used for valuation",
    )
