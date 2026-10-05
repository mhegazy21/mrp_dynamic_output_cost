# -*- coding: utf-8 -*-
{
    'name': 'MRP Butcher Test - Dynamic Output Cost Allocation',
    'version': '20.0.1.0.1',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Dynamic output cost allocation and inventory valuation for Butcher Test BoMs',
    'description': """
MRP Butcher Test – Dynamic Output Cost Allocation & Inventory Valuation
========================================================================
Dynamically allocates actual manufacturing cost (components + operations)
across multiple outputs (main product and by-products) based on actual
produced quantities and Relative Importance % configured on the BoM.
    """,
    'author': 'mhegazy21',
    'website': 'https://github.com/mhegazy21',
    'depends': [
        'mrp',
        'mrp_account',
        'stock_account',
    ],
    'data': [
        'security/ir.access.csv',
        'views/mrp_bom_views.xml',
        'views/mrp_production_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'price': 49.00,
    'currency': 'USD',
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
