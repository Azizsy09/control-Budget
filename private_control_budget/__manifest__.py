# Migrate v14 by Optesis-CTD
{
    'name': 'optesis_account_bugdet_control ',
    'author': 'OPTESIS SA',
    'version': '17.0',
    'category': 'Tools',
    'description': """
Ce module permet de faire le control budgetaire pour le secteur privé
""",
    'summary': 'Comptabilite',
    'sequence': 9,
    'depends': ['base','account','account_reports','analytic','account_budget','purchase','report_xlsx'],
    'data': [
        
       
        'security/group_control_gestion.xml',
         'security/ir.model.access.csv',
        'views/account_budget_view.xml',
        'views/menu_view.xml',
        'reports/reports.xml',
        
        'views/account_analytic_account_view.xml',
       
         'views/purchase_view.xml',
        
       
        
    ],
    'test': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
