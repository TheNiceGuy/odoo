# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


{
    'name': 'PosBox Screen',
    'version': '1.0',
    'category': 'Hardware Drivers',
    'website': 'https://www.odoo.com/page/point-of-sale',
    'summary': 'A kiosk screen for the PosBox',
    'description': """
PosBox Homepage
===============

This module manage communications between the POS interface and the embedded kiosk navigator

""",
    'author': 'Odoo SA',
    'depends': ['hw_proxy'], 
    'installable': False,
    'auto_install': False,
}
