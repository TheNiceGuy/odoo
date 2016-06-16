# -*- coding: utf-8 -*-
import datetime
import werkzeug

from collections import OrderedDict

from openerp import fields, SUPERUSER_ID
from openerp.addons.web import http
from openerp.addons.web.http import request
from openerp.addons.website.models.website import slug, unslug
from openerp.addons.website_partner.controllers.main import WebsitePartnerPage
from openerp.tools.translate import _

from openerp.addons.website_portal.controllers.main import website_account


class WebsiteAccount(website_account):

    @http.route()
    def account(self):
        response = super(WebsiteAccount, self).account()
        lead_count = request.env['crm.lead'].search_count([])
        response.qcontext.update({'lead_count': lead_count})
        return response

    @http.route(['/my/leads', '/my/leads/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_leads(self, page=1, date_begin=None, date_end=None, lead=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        CrmLead = request.env['crm.lead']

        today = fields.Date.today()

        filters = {
            'all': {'label': _('All'), 'domain': []},
            'today': {'label': _('Today Activities'), 'domain': [('date_action', '=', today)]},
            'week': {'label': _('This Week Activities'),
                     'domain': ['&', ('date_action', '>=', today),
                                ('date_action', '<=', (fields.Date.from_string(today) + datetime.timedelta(days=7)))]},
            'overdue': {'label': _('Overdue Activities'), 'domain': [('date_action', '<', today)]},
            'won': {'label': _('Won'), 'domain': ['&', ('stage_id.probability', '=', 100), ('stage_id.fold', '=', True)]},
            'lost': {'label': _('Lost'), 'domain': [('active', '=', False)]},
        }

        sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'name': {'label': _('Name'), 'order': 'name'},
            'customer': {'label': _('Customer'), 'order': 'partner_id'},
            'revenue': {'label': _('Expected Revenue'), 'order': 'planned_revenue desc'},
            'probability': {'label': _('Probability'), 'order': 'probability desc'},
            'stage': {'label': _('Stage'), 'order': 'stage_id'},
        }

        domain = filters.get(lead, filters['all'])['domain']
        order = sortings.get(sortby, sortings['date'])['order']

        # archive groups - Default Group By 'create_date'
        archive_groups = self._get_archive_groups('crm.lead', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]
        # pager
        lead_count = CrmLead.search_count(domain)
        pager = request.website.pager(
            url="/my/leads",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=lead_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        leads = CrmLead.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'date': date_begin,
            'leads': leads,
            'page_name': 'lead',
            'filters': OrderedDict(sorted(filters.items())),
            'lead': lead,
            'sortings': sortings,
            'sortby': sortby,
            'archive_groups': archive_groups,
            'default_url': '/my/leads',
            'pager': pager
        })
        return request.website.render("website_crm_partner_assign.portal_my_leads", values)

    @http.route(['/my/lead/<model("crm.lead"):lead>'], type='http', auth="user", website=True)
    def leads_followup(self, lead=None, **kw):
        return request.website.render("website_crm_partner_assign.leads_followup", {'lead': lead})


class WebsiteCrmPartnerAssign(WebsitePartnerPage):
    _references_per_page = 40

    @http.route([
        '/partners',
        '/partners/page/<int:page>',

        '/partners/grade/<model("res.partner.grade"):grade>',
        '/partners/grade/<model("res.partner.grade"):grade>/page/<int:page>',

        '/partners/country/<model("res.country"):country>',
        '/partners/country/<model("res.country"):country>/page/<int:page>',

        '/partners/grade/<model("res.partner.grade"):grade>/country/<model("res.country"):country>',
        '/partners/grade/<model("res.partner.grade"):grade>/country/<model("res.country"):country>/page/<int:page>',
    ], type='http', auth="public", website=True)
    def partners(self, country=None, grade=None, page=0, **post):
        country_all = post.pop('country_all', False)
        partner_obj = request.registry['res.partner']
        country_obj = request.registry['res.country']
        search = post.get('search', '')

        base_partner_domain = [('is_company', '=', True), ('grade_id', '!=', False), ('website_published', '=', True)]
        if not request.registry['res.users'].has_group(request.cr, request.uid, 'base.group_website_publisher'):
            base_partner_domain += [('grade_id.website_published', '=', True)]
        if search:
            base_partner_domain += ['|', ('name', 'ilike', search), ('website_description', 'ilike', search)]

        # group by grade
        grade_domain = list(base_partner_domain)
        if not country and not country_all:
            country_code = request.session['geoip'].get('country_code')
            if country_code:
                country_ids = country_obj.search(request.cr, request.uid, [('code', '=', country_code)], context=request.context)
                if country_ids:
                    country = country_obj.browse(request.cr, request.uid, country_ids[0], context=request.context)
        if country:
            grade_domain += [('country_id', '=', country.id)]
        grades = partner_obj.read_group(
            request.cr, SUPERUSER_ID, grade_domain, ["id", "grade_id"],
            groupby="grade_id", orderby="grade_id DESC", context=request.context)
        grades_partners = partner_obj.search(
            request.cr, SUPERUSER_ID, grade_domain,
            context=request.context, count=True)
        # flag active grade
        for grade_dict in grades:
            grade_dict['active'] = grade and grade_dict['grade_id'][0] == grade.id
        grades.insert(0, {
            'grade_id_count': grades_partners,
            'grade_id': (0, _("All Categories")),
            'active': bool(grade is None),
        })

        # group by country
        country_domain = list(base_partner_domain)
        if grade:
            country_domain += [('grade_id', '=', grade.id)]
        countries = partner_obj.read_group(
            request.cr, SUPERUSER_ID, country_domain, ["id", "country_id"],
            groupby="country_id", orderby="country_id", context=request.context)
        countries_partners = partner_obj.search(
            request.cr, SUPERUSER_ID, country_domain,
            context=request.context, count=True)
        # flag active country
        for country_dict in countries:
            country_dict['active'] = country and country_dict['country_id'] and country_dict['country_id'][0] == country.id
        countries.insert(0, {
            'country_id_count': countries_partners,
            'country_id': (0, _("All Countries")),
            'active': bool(country is None),
        })

        # current search
        if grade:
            base_partner_domain += [('grade_id', '=', grade.id)]
        if country:
            base_partner_domain += [('country_id', '=', country.id)]

        # format pager
        if grade and not country:
            url = '/partners/grade/' + slug(grade)
        elif country and not grade:
            url = '/partners/country/' + slug(country)
        elif country and grade:
            url = '/partners/grade/' + slug(grade) + '/country/' + slug(country)
        else:
            url = '/partners'
        url_args = {}
        if search:
            url_args['search'] = search
        if country_all:
            url_args['country_all'] = True

        partner_count = partner_obj.search_count(
            request.cr, SUPERUSER_ID, base_partner_domain,
            context=request.context)
        pager = request.website.pager(
            url=url, total=partner_count, page=page, step=self._references_per_page, scope=7,
            url_args=url_args)

        # search partners matching current search parameters
        partner_ids = partner_obj.search(
            request.cr, SUPERUSER_ID, base_partner_domain,
            order="grade_id DESC, display_name ASC",
            context=request.context)  # todo in trunk: order="grade_id DESC, implemented_count DESC", offset=pager['offset'], limit=self._references_per_page
        partners = partner_obj.browse(request.cr, SUPERUSER_ID, partner_ids, request.context)
        # remove me in trunk
        partners = sorted(partners, key=lambda x: (x.grade_id.sequence if x.grade_id else 0, len([i for i in x.implemented_partner_ids if i.website_published])), reverse=True)
        partners = partners[pager['offset']:pager['offset'] + self._references_per_page]

        google_map_partner_ids = ','.join(map(str, [p.id for p in partners]))

        values = {
            'countries': countries,
            'current_country': country,
            'grades': grades,
            'current_grade': grade,
            'partners': partners,
            'google_map_partner_ids': google_map_partner_ids,
            'pager': pager,
            'searches': post,
            'search_path': "%s" % werkzeug.url_encode(post),
        }
        return request.render("website_crm_partner_assign.index", values, status=partners and 200 or 404)


    # Do not use semantic controller due to SUPERUSER_ID
    @http.route(['/partners/<partner_id>'], type='http', auth="public", website=True)
    def partners_detail(self, partner_id, **post):
        _, partner_id = unslug(partner_id)
        current_grade, current_country = None, None
        grade_id = post.get('grade_id')
        country_id = post.get('country_id')
        if grade_id:
            grade_ids = request.registry['res.partner.grade'].exists(request.cr, request.uid, int(grade_id), context=request.context)
            if grade_ids:
                current_grade = request.registry['res.partner.grade'].browse(request.cr, request.uid, grade_ids[0], context=request.context)
        if country_id:
            country_ids = request.registry['res.country'].exists(request.cr, request.uid, int(country_id), context=request.context)
            if country_ids:
                current_country = request.registry['res.country'].browse(request.cr, request.uid, country_ids[0], context=request.context)
        if partner_id:
            partner = request.registry['res.partner'].browse(request.cr, SUPERUSER_ID, partner_id, context=request.context)
            is_website_publisher = request.registry['res.users'].has_group(request.cr, request.uid, 'base.group_website_publisher')
            if partner.exists() and (partner.website_published or is_website_publisher):
                values = {
                    'main_object': partner,
                    'partner': partner,
                    'current_grade': current_grade,
                    'current_country': current_country
                }
                return request.website.render("website_crm_partner_assign.partner", values)
        return self.partners(**post)
