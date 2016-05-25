# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
try:
    import cPickle as pickle
except ImportError:
    import pickle
from itertools import groupby
from lxml import etree
from operator import itemgetter
import os
import random

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.release import version_info
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

FIELD_STATES = [('clear', 'Clear'), ('anonymized', 'Anonymized'), ('not_existing', 'Not Existing'), ('new', 'New')]
ANONYMIZATION_STATES = FIELD_STATES + [('unstable', 'Unstable')]
WIZARD_ANONYMIZATION_STATES = [('clear', 'Clear'), ('anonymized', 'Anonymized'), ('unstable', 'Unstable')]
ANONYMIZATION_HISTORY_STATE = [('started', 'Started'), ('done', 'Done'), ('in_exception', 'Exception occured')]
ANONYMIZATION_DIRECTION = [('clear -> anonymized', 'clear -> anonymized'), ('anonymized -> clear', 'anonymized -> clear')]


def group(lst, cols):
    if isinstance(cols, basestring):
        cols = [cols]
    return dict((k, [v for v in itr]) for k, itr in groupby(sorted(lst, key=itemgetter(*cols)), itemgetter(*cols)))


class IrModelFieldsAnonymization(models.Model):
    _name = 'ir.model.fields.anonymization'
    _rec_name = 'field_id'

    model_name = fields.Char('Object Name', required=True)
    model_id = fields.Many2one('ir.model', string='Object', ondelete='set null')
    field_name = fields.Char(required=True)
    field_id = fields.Many2one('ir.model.fields', string='Field', ondelete='set null')
    state = fields.Selection(selection=FIELD_STATES, string='Status', required=True, readonly=True, default='clear')

    _sql_constraints = [
        ('model_id_field_id_uniq', 'unique (model_name, field_name)', _("You cannot have two fields with the same name on the same object!")),
    ]

    def _get_global_state(self):
        ano_fields = self.search([('state', '!=', 'not_existing')])
        if not len(ano_fields) or len(ano_fields) == len(ano_fields.filtered(lambda f: f.state == "clear")):
            state = 'clear'  # all fields are clear
        elif len(ano_fields) == len(ano_fields.filtered(lambda f: f.state == "anonymized")):
            state = 'anonymized'  # all fields are anonymized
        else:
            state = 'unstable'  # fields are mixed: this should be fixed
        return state

    def _check_write(self):
        """check that the field is created from the menu and not from an database update
           otherwise the database update can crash:"""
        if self.env.context.get('manual'):
            global_state = self._get_global_state()
            if global_state == 'anonymized':
                raise UserError(_("The database is currently anonymized, you cannot create, modify or delete fields."))
            elif global_state == 'unstable':
                raise UserError(_("The database anonymization is currently in an unstable state. Some fields are anonymized,"
                                " while some fields are not anonymized. You should try to solve this problem before trying to create, write or delete fields."))
        return True

    def _get_model_and_field_ids(self, vals):
        if vals.get('field_name') and vals.get('model_name'):
            model_id = self.env['ir.model'].search([('model', '=', vals['model_name'])], limit=1).id
            if model_id:
                field_id = self.env['ir.model.fields'].search([('name', '=', vals['field_name']), ('model_id', '=', model_id)], limit=1).id
                if field_id:
                    return (model_id, field_id)
        return (False, False)

    @api.model
    def create(self, vals):
        # check field state: all should be clear before we can add a new field to anonymize:
        self._check_write()
        if vals.get('field_name') and vals.get('model_name'):
            vals['model_id'], vals['field_id'] = self._get_model_and_field_ids(vals)
        # check not existing fields:
        vals['state'] = not vals.get('field_id') and 'not_existing' or self._get_global_state()
        return super(IrModelFieldsAnonymization, self).create(vals)

    @api.multi
    def write(self, vals):
        # check field state: all should be clear before we can modify a field:
        if not (len(vals.keys()) == 1 and vals.get('state') == 'clear'):
            self._check_write()
        if vals.get('field_name') and vals.get('model_name'):
            vals['model_id'], vals['field_id'] = self._get_model_and_field_ids(vals)
        # check not existing fields:
        if vals.get('field_id'):
            if not vals.get('field_id'):
                vals['state'] = 'not_existing'
            else:
                global_state = self._get_global_state()
                if global_state != 'unstable':
                    vals['state'] = global_state
        return super(IrModelFieldsAnonymization, self).write(vals)

    @api.multi
    def unlink(self):
        # check field state: all should be clear before we can unlink a field:
        self._check_write()
        return super(IrModelFieldsAnonymization, self).unlink()

    @api.onchange('model_id')
    def onchange_model_id(self):
        self.field_name = False
        self.field_id = False
        self.model_name = False
        if self.model_id:
            self.model_name = self.model_id.model

    @api.onchange('model_name')
    def onchange_model_name(self):
        self.field_name = False
        self.field_id = False
        self.model_id = False
        if self.model_name:
            self.model_id = self.env['ir.model'].search([('model', '=', self.model_name)], limit=1)

    @api.onchange('field_name', 'model_name')
    def onchange_field_name(self):
        self.field_id = False
        if self.field_name and self.model_name:
            self.field_id = self.env['ir.model.fields'].search([('name', '=', self.field_name), ('model', '=', self.model_name)], limit=1)

    @api.onchange('field_id', 'model_name')
    def onchange_field_id(self):
        self.field_name = False
        if self.field_id:
            self.field_name = self.field_id.name


class IrModelFieldsAnonymizationHistory(models.Model):
    _name = 'ir.model.fields.anonymization.history'
    _order = "date desc"

    date = fields.Datetime(required=True, readonly=True)
    field_ids = fields.Many2many('ir.model.fields.anonymization', 'anonymized_field_to_history_rel', 'field_id', 'history_id', string='Fields', readonly=True)
    state = fields.Selection(selection=ANONYMIZATION_HISTORY_STATE, string='Status', required=True, readonly=True)
    direction = fields.Selection(selection=ANONYMIZATION_DIRECTION, required=True, readonly=True)
    msg = fields.Text('Message', readonly=True)
    filepath = fields.Char('File path', readonly=True)


class IrModelFieldsAnonymizeWizard(models.TransientModel):
    _name = 'ir.model.fields.anonymize.wizard'

    def _get_state(self):
        self.state = self._get_state_value()

    def _get_summary(self):
        self.summary = self._get_summary_value()

    name = fields.Char('File Name')
    summary = fields.Text(compute='_get_summary')
    file_export = fields.Binary('Export')
    file_import = fields.Binary('Import', help="This is the file created by the anonymization process. It should have the '.pickle' extention.")
    state = fields.Selection(compute='_get_state', string='Status', selection=WIZARD_ANONYMIZATION_STATES, readonly=False)
    msg = fields.Text('Message')

    def _get_state_value(self):
        return self.env['ir.model.fields.anonymization']._get_global_state()

    def _get_summary_value(self):
        summary = u''
        for anon_field in self.env['ir.model.fields.anonymization'].search([('state', '!=', 'not_existing')]):
            values = {
                'model_name': anon_field.model_id.name,
                'model_code': anon_field.model_id.model,
                'field_code': anon_field.field_id.name,
                'field_name': anon_field.field_id.field_description,
                'state': anon_field.state,
            }
            summary += u" * %(model_name)s (%(model_code)s) -> %(field_name)s (%(field_code)s): state: (%(state)s)\n" % values
        return summary

    @api.model
    def default_get(self, fields):
        res = {}
        res['name'] = '.pickle'
        res['summary'] = self._get_summary_value()
        res['state'] = self._get_state_value()
        res['msg'] = _("Before executing the anonymization process, you should make a backup of your database.")
        return res

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        state = self.env['ir.model.fields.anonymization']._get_global_state()
        step = self.env.context.get('step', 'new_window')
        res = super(IrModelFieldsAnonymizeWizard, self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        eview = etree.fromstring(res['arch'])
        placeholder = eview.xpath("group[@name='placeholder1']")
        if len(placeholder):
            placeholder = placeholder[0]
            if step == 'new_window' and state == 'clear':
                # clicked in the menu and the fields are not anonymized: warn the admin that backuping the db is very important
                placeholder.addnext(etree.Element('field', {'name': 'msg', 'colspan': '4', 'nolabel': '1'}))
                placeholder.addnext(etree.Element('newline'))
                placeholder.addnext(etree.Element('label', {'string': 'Warning'}))
                eview.remove(placeholder)
            elif step == 'new_window' and state == 'anonymized':
                # clicked in the menu and the fields are already anonymized
                placeholder.addnext(etree.Element('newline'))
                placeholder.addnext(etree.Element('field', {'name': 'file_import', 'required': "1"}))
                placeholder.addnext(etree.Element('label', {'string': 'Anonymization file'}))
                eview.remove(placeholder)
            elif step == 'just_anonymized':
                # we just ran the anonymization process, we need the file export field
                placeholder.addnext(etree.Element('newline'))
                placeholder.addnext(etree.Element('field', {'name': 'file_export'}))
                # we need to remove the button:
                buttons = eview.xpath("button")
                for button in buttons:
                    eview.remove(button)
                # and add a message:
                placeholder.addnext(etree.Element('field', {'name': 'msg', 'colspan': '4', 'nolabel': '1'}))
                placeholder.addnext(etree.Element('newline'))
                placeholder.addnext(etree.Element('label', {'string': 'Result'}))
                # remove the placeholer:
                eview.remove(placeholder)
            elif step == 'just_desanonymized':
                # we just reversed the anonymization process, we don't need any field
                # we need to remove the button
                buttons = eview.xpath("button")
                for button in buttons:
                    eview.remove(button)
                # and add a message
                # and add a message:
                placeholder.addnext(etree.Element('field', {'name': 'msg', 'colspan': '4', 'nolabel': '1'}))
                placeholder.addnext(etree.Element('newline'))
                placeholder.addnext(etree.Element('label', {'string': 'Result'}))
                # remove the placeholer:
                eview.remove(placeholder)
            else:
                raise UserError(_("The database anonymization is currently in an unstable state. Some fields are anonymized,"
                                " while some fields are not anonymized. You should try to solve this problem before trying to do anything else."))
            res['arch'] = etree.tostring(eview)
        return res

    def _raise_after_history_update(self, history, error_type, error_msg):
        history.state = 'in_exception'
        history.msg = error_msg
        raise UserError('%s: %s' % (error_type, error_msg))

    @api.multi
    def anonymize_database(self):
        """Sets the 'anonymized' state to defined fields"""
        self.ensure_one()

        # create a new history record:
        history = self.env['ir.model.fields.anonymization.history'].create({
            'date': fields.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'started',
            'direction': 'clear -> anonymized'
        })

        # check that all the defined fields are in the 'clear' state
        state = self.env['ir.model.fields.anonymization']._get_global_state()
        if state == 'anonymized':
            self._raise_after_history_update(history, _('Error !'), _("The database is currently anonymized, you cannot anonymize it again."))
        elif state == 'unstable':
            self._raise_after_history_update(history, _('Error !'), _("The database anonymization is currently in an unstable state. Some fields are anonymized,"
                                                                      " while some fields are not anonymized. You should try to solve this problem before trying to do anything."))

        # do the anonymization:
        dirpath = os.environ.get('HOME') or os.getcwd()
        rel_filepath = 'field_anonymization_%s_%s.pickle' % (self.env.cr.dbname, history.id)
        abs_filepath = os.path.abspath(os.path.join(dirpath, rel_filepath))

        ano_fields = self.env['ir.model.fields.anonymization'].search([('state', '!=', 'not_existing')])
        if not ano_fields:
            self._raise_after_history_update(history, _('Error !'), _("No fields are going to be anonymized."))

        data = []

        for field in ano_fields:
            model_name = field.model_id.model
            field_name = field.field_id.name
            field_type = field.field_id.ttype
            table_name = self.env[model_name]._table

            # get the current value
            sql = "select id, %s from %s" % (field_name, table_name)
            self.env.cr.execute(sql)
            for record in self.env.cr.dictfetchall():
                data.append({"model_id": model_name, "field_id": field_name, "id": record['id'], "value": record[field_name]})

                # anonymize the value:
                anonymized_value = None

                sid = str(record['id'])
                if field_type == 'char':
                    anonymized_value = 'xxx'+sid
                elif field_type == 'selection':
                    anonymized_value = 'xxx'+sid
                elif field_type == 'text':
                    anonymized_value = 'xxx'+sid
                elif field_type == 'boolean':
                    anonymized_value = random.choice([True, False])
                elif field_type == 'date':
                    anonymized_value = '2011-11-11'
                elif field_type == 'datetime':
                    anonymized_value = '2011-11-11 11:11:11'
                elif field_type == 'float':
                    anonymized_value = 0.0
                elif field_type == 'integer':
                    anonymized_value = 0
                elif field_type in ['binary', 'many2many', 'many2one', 'one2many', 'reference']:  # cannot anonymize these kind of fields
                    self._raise_after_history_update(history, _('Error !'), _("Cannot anonymize fields of these types: binary, many2many, many2one, one2many, reference."))

                if anonymized_value is None:
                    self._raise_after_history_update(history, _('Error !'), _("Anonymized value can not be empty."))

                sql = "update %(table)s set %(field)s = %%(anonymized_value)s where id = %%(id)s" % {
                    'table': table_name,
                    'field': field_name
                }
                self.env.cr.execute(sql, {
                    'anonymized_value': anonymized_value,
                    'id': record['id']
                })

        # save pickle:
        fn = open(abs_filepath, 'w')
        pickle.dump(data, fn, pickle.HIGHEST_PROTOCOL)

        # update the anonymization fields:
        ano_fields.write({'state': 'anonymized'})

        # add a result message in the wizard:
        msgs = ["Anonymization successful.",
                "",
                "Donot forget to save the resulting file to a safe place because you will not be able to revert the anonymization without this file.",
                "",
                "This file is also stored in the %s directory. The absolute file path is: %s."
                ]
        msg = '\n'.join(msgs) % (dirpath, abs_filepath)

        fn = open(abs_filepath, 'r')

        self.write({
            'msg': msg,
            'file_export': base64.encodestring(fn.read())
        })

        fn.close()

        # update the history record:
        history.write({
            'field_ids': [[6, 0, ano_fields.ids]],
            'msg': msg,
            'filepath': abs_filepath,
            'state': 'done'
        })

        return {
            'res_id': self.id,
            'view_id': self.env.ref('anonymization.ir_model_fields_anonymize_wizard_view_form').id,
            'view_type': 'form',
            "view_mode": 'form',
            'res_model': 'ir.model.fields.anonymize.wizard',
            'type': 'ir.actions.act_window',
            'context': {'step': 'just_anonymized'},
            'target': 'new'
        }

    @api.multi
    def reverse_anonymize_database(self):
        """Set the 'clear' state to defined fields"""
        self.ensure_one()
        IrModelFieldsAnonymization = self.env['ir.model.fields.anonymization']

        # create a new history record:
        history = self.env['ir.model.fields.anonymization.history'].create({
            'date': fields.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'started',
            'direction': 'anonymized -> clear'
        })

        # check that all the defined fields are in the 'anonymized' state
        state = IrModelFieldsAnonymization._get_global_state()
        if state == 'clear':
            raise UserError(_("The database is not currently anonymized, you cannot reverse the anonymization."))
        elif state == 'unstable':
            raise UserError(_("The database anonymization is currently in an unstable state. Some fields are anonymized,"
                            " while some fields are not anonymized. You should try to solve this problem before trying to do anything."))

        for wizard in self:
            if not wizard.file_import:
                self._raise_after_history_update(history, _('Error !'), _("It is not possible to reverse the anonymization process without supplying the anonymization export file."))

            # reverse the anonymization:
            # load the pickle file content into a data structure:
            data = pickle.loads(base64.decodestring(wizard.file_import))

            MigrationFix = self.env['ir.model.fields.anonymization.migration.fix']
            fixes = MigrationFix.search_read([('target_version', '=', '.'.join(map(str, version_info[:2])))], ['model_name', 'field_name', 'query', 'query_type', 'sequence'])
            fixes = group(fixes, ('model_name', 'field_name'))

            for line in data:
                queries = []
                table_name = self.env[line['model_id']]._table if line['model_id'] in self.env else None

                # check if custom sql exists:
                key = (line['model_id'], line['field_id'])
                custom_updates = fixes.get(key)
                if custom_updates:
                    custom_updates.sort(key=itemgetter('sequence'))
                    queries = [(record['query'], record['query_type']) for record in custom_updates if record['query_type']]
                elif table_name:
                    queries = [("update %(table)s set %(field)s = %%(value)s where id = %%(id)s" % {
                        'table': table_name,
                        'field': line['field_id'],
                    }, 'sql')]

                for query in queries:
                    if query[1] == 'sql':
                        self.env.cr.execute(query[0], {
                            'value': line['value'],
                            'id': line['id']
                        })
                    elif query[1] == 'python':
                        eval(query[0] % line)
                    else:
                        raise Exception("Unknown query type '%s'. Valid types are: sql, python." % (query['query_type'], ))

            # update the anonymization fields:
            ano_fields = IrModelFieldsAnonymization.search([('state', '!=', 'not_existing')])
            ano_fields.write({'state': 'clear'})

            # add a result message in the wizard:
            self.msg = '\n'.join(["Successfully reversed the anonymization.", ""])

            # update the history record:
            history.write({
                'field_ids': [[6, 0, ano_fields.ids]],
                'msg': self.msg,
                'filepath': False,
                'state': 'done'
            })

            return {
                'res_id': self.id,
                'view_id': self.env.ref('anonymization.ir_model_fields_anonymize_wizard_view_form').id,
                'view_type': 'form',
                "view_mode": 'form',
                'res_model': 'ir.model.fields.anonymize.wizard',
                'type': 'ir.actions.act_window',
                'context': {'step': 'just_desanonymized'},
                'target': 'new'
            }

    def _id_get(self, cr, uid, model, id_str, mod):
        if '.' in id_str:
            mod, id_str = id_str.split('.')
        try:
            idn = self.pool.get('ir.model.data')._get_id(cr, uid, mod, id_str)
            res = int(self.pool.get('ir.model.data').read(cr, uid, [idn], ['res_id'])[0]['res_id'])
        except:
            res = None
        return res


class IrModelFieldsAnonymizationMigrationFix(models.Model):
    _name = 'ir.model.fields.anonymization.migration.fix'
    _order = "sequence"

    target_version = fields.Char()
    model_name = fields.Char('Model')
    field_name = fields.Char('Field')
    query = fields.Text()
    query_type = fields.Selection(selection=[('sql', 'sql'), ('python', 'python')], string='Query')
    sequence = fields.Integer()
