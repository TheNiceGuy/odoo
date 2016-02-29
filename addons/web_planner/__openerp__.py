# -*- coding: utf-8 -*-
{
    'name': 'Planner',
    'category': 'Planner',
    'summary': 'Help to configure application',
    'version': '1.0',
    'description': """Application Planner""",
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'security/web_planner_security.xml',
        'views/web_planner_templates.xml',
        'views/web_planner_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
