# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    butcher_test = fields.Boolean(
        string='Butcher Test',
        default=False,
        help="If enabled, uses dynamic Butcher Test costing across outputs based on actual produced quantities."
    )
    butcher_output_ids = fields.One2many(
        'mrp.bom.butcher.output',
        'bom_id',
        string='Butcher Test Outputs',
        copy=True,
    )

    def _get_expected_butcher_products(self):
        self.ensure_one()
        products = self.env['product.product']
        if self.product_id:
            products |= self.product_id
        elif self.product_tmpl_id:
            products |= self.product_tmpl_id.product_variant_ids
        for bp in self.byproduct_ids:
            if bp.product_id:
                products |= bp.product_id
        return products

    def action_sync_butcher_outputs(self):
        self.ensure_one()
        expected_products = self._get_expected_butcher_products()
        existing_products = self.butcher_output_ids.mapped('product_id')
        new_lines = []
        for product in expected_products:
            if product not in existing_products:
                new_lines.append((0, 0, {
                    'product_id': product.id,
                    'relative_importance': 0.0,
                }))
        if new_lines:
            self.write({'butcher_output_ids': new_lines})
        return True

    @api.onchange('butcher_test', 'product_tmpl_id', 'product_id', 'byproduct_ids')
    def _onchange_butcher_test_outputs(self):
        if self.butcher_test and self.type == 'normal':
            expected_products = self._get_expected_butcher_products()
            existing_products = self.butcher_output_ids.mapped('product_id')
            new_lines = []
            for product in expected_products:
                if product not in existing_products:
                    new_lines.append((0, 0, {
                        'product_id': product.id,
                        'relative_importance': 0.0,
                    }))
            if new_lines:
                self.butcher_output_ids = new_lines

    @api.constrains('butcher_test', 'type', 'butcher_output_ids', 'product_tmpl_id', 'product_id', 'byproduct_ids')
    def _check_butcher_test_configuration(self):
        for bom in self:
            if not bom.butcher_test:
                continue

            if bom.type != 'normal':
                raise ValidationError(_("Butcher Test costing is only allowed for BoMs of type 'Manufacture this product'."))

            if not bom.butcher_output_ids:
                raise ValidationError(_("Butcher Test is enabled, but no outputs are configured in the 'Butcher Test Outputs' tab."))

            expected_products = bom._get_expected_butcher_products()
            configured_products = bom.butcher_output_ids.mapped('product_id')
            missing_products = expected_products - configured_products
            if missing_products:
                names = ", ".join(missing_products.mapped('display_name'))
                raise ValidationError(_("The 'Butcher Test Outputs' tab must contain all output products (main product and by-products). Missing: %s", names))

            for line in bom.butcher_output_ids:
                if line.relative_importance <= 0:
                    raise ValidationError(_("Relative Importance (%%) must be greater than zero for product '%s'.", line.product_id.display_name))


class MrpBomButcherOutput(models.Model):
    _name = 'mrp.bom.butcher.output'
    _description = 'BoM Butcher Test Output'
    _order = 'bom_id, id'

    _bom_product_unique = models.Constraint(
        'unique(bom_id, product_id)',
        'Output product must be unique per BoM!'
    )

    bom_id = fields.Many2one('mrp.bom', string='BoM', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    relative_importance = fields.Float(
        string='Relative Importance (%)',
        default=0.0,
        digits=(16, 4),
        required=True,
        help="Weighting factor combined with actual produced quantity to determine dynamic cost allocation."
    )
