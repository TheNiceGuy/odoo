# -*- coding: utf-8 -*-

import werkzeug
from openerp import http
from openerp.http import request


class Rating(http.Controller):

    @http.route('/rating/<string:token>/<int:rate>', type='http', auth="public")
    def add_rating(self, token, rate, **kwargs):
        token_rec = request.env['rating.token'].sudo().search([('access_token', '=', token)])
        if token_rec:
            is_rated = bool(token_rec.rating_id.rating != -1) if token_rec.rating_id.rating else False
            if not is_rated:
                record_sudo = request.env[token_rec.res_model].sudo().browse(token_rec.res_id)
                record_sudo.rating_apply(rate, token=token)
            return request.render('rating.rating_external_page_view', {'rating': rate, 'is_rated': is_rated, 'token': token})
        return request.not_found()

    @http.route(['/rating/<string:token>/feedback', '/rating/<string:token>/cancel'], type="http", auth="public", method=['post'])
    def add_feedback(self, token, **kwargs):
        token_rec = request.env['rating.token'].sudo().search([('access_token', '=', token)])
        if token_rec:
            if kwargs.get('feedback'):
                token_rec.rating_id.sudo().write({'feedback': kwargs.get('feedback')})
            # redirect to the form view if logged person
            if request.session.uid:
                record_sudo = request.env[token_rec.res_model].sudo().browse(token_rec.res_id)
                return werkzeug.utils.redirect('/web#model=%s&id=%s&view_type=form' % (record_sudo._name, record_sudo.id))
            return request.render('rating.rating_external_page_view', {'is_public': True})
        return request.not_found()
