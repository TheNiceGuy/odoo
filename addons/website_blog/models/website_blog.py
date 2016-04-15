# -*- coding: utf-8 -*-

from datetime import datetime
import json
import lxml
import random

from odoo import api, fields, models
from odoo.tools.translate import _, html_translate

from openerp.addons.website.models.website import slug


class Blog(models.Model):

    _name = 'blog.blog'
    _description = 'Blogs'
    _inherit = ['mail.thread', 'website.seo.metadata']
    _order = 'name'

    name = fields.Char('Blog Name', required=True, translate=True)
    subtitle = fields.Char('Blog Subtitle', translate=True)
    active = fields.Boolean('Active', default=True)

    @api.multi
    def write(self, vals):
        result = super(Blog, self).write(vals)
        if 'active' in vals:
            # archiving/unarchiving a blog does it on its posts, too
            posts = self.env['blog.post'].with_context(active_test=False).search([('blog_id', 'in', self.ids)])
            posts.write({'active': vals['active']})
        return result

    @api.multi
    def all_tags(self, min_limit=1):
        """ Returns the tags related to the post of each given blog """
        query = """
            SELECT
                p.blog_id, count(*), r.blog_tag_id
            FROM
                blog_post_blog_tag_rel r
                    join blog_post p on r.blog_post_id=p.id
            WHERE
                p.blog_id in %s
            GROUP BY
                p.blog_id,
                r.blog_tag_id
            ORDER BY
                count(*) DESC
        """
        self.env.cr.execute(query, [tuple(self.ids)])
        tag_by_blog = dict((blog_id, []) for blog_id in self.ids)
        for blog_id, freq, tag_id in self.env.cr.fetchall():
            if freq >= min_limit:
                tag_by_blog[blog_id].append(tag_id)

        Tag = self.env['blog.tag']
        for blog_id in tag_by_blog:
            tag_by_blog[blog_id] = Tag.browse(tag_by_blog[blog_id])
        return tag_by_blog


class BlogTag(models.Model):

    _name = 'blog.tag'
    _description = 'Blog Tag'
    _inherit = ['website.seo.metadata']
    _order = 'name'

    name = fields.Char('Name', required=True)
    post_ids = fields.Many2many('blog.post', string='Posts')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists !"),
    ]


class BlogPost(models.Model):

    _name = "blog.post"
    _description = "Blog Post"
    _inherit = ['mail.thread', 'website.seo.metadata', 'website.published.mixin']
    _order = 'id DESC'
    _mail_post_access = 'read'

    @api.model
    def _default_author(self):
        return self.env.user.partner_id.id

    @api.model
    def _default_content(self):
        return '''  <div class="container">
                        <section class="mt16 mb16">
                            <p class="o_default_snippet_text">''' + _("Start writing here...") + '''</p>
                        </section>
                    </div> '''

    @api.model
    def _default_cover_properties(self):
        return json.dumps({
            "background-image": "none",
            "background-color": "oe_none",
            "opacity": "0.6",
            "resize_class": ""
        })

    name = fields.Char('Title', required=True, translate=True, default="")
    subtitle = fields.Char('Sub Title', translate=True)
    author_id = fields.Many2one('res.partner', 'Author', default=_default_author)
    active = fields.Boolean('Active', default=True)
    cover_properties = fields.Text('Cover Properties', default=_default_cover_properties)
    blog_id = fields.Many2one('blog.blog', 'Blog', required=True, ondelete='cascade')
    tag_ids = fields.Many2many('blog.tag', string='Tags')
    content = fields.Html('Content', translate=html_translate, sanitize=False, default=_default_content)
    website_message_ids = fields.One2many('mail.message', 'res_id',
        domain=lambda self: [
            '&', '&', ('model', '=', self._name), ('message_type', '=', 'comment'), ('path', '=', False)
        ],
        string='Website Messages',
        help="Website communication history",
    )
    # creation / update stuff
    create_date = fields.Datetime('Created on', index=True, readonly=True)
    create_uid = fields.Many2one('res.users', 'Author', index=True, readonly=True)
    write_date = fields.Datetime('Last Modified on', index=True, readonly=True)
    write_uid = fields.Many2one('res.users', 'Last Contributor', index=True, readonly=True)
    author_avatar = fields.Binary('Avatar', related='author_id.image_small')
    visits = fields.Integer('No of Views')
    ranking = fields.Float('Ranking', compute='_compute_ranking')

    @api.multi
    def _website_url(self, field_name, arg):
        result = super(BlogPost, self)._website_url(field_name, arg)
        for blog_post in self:
            result[blog_post.id] = "/blog/%s/post/%s" % (slug(blog_post.blog_id), slug(blog_post))
        return result

    @api.multi
    def _compute_ranking(self):
        for blog_post in self:
            age = datetime.now() - fields.Datetime.from_string(blog_post.create_date)
            blog_post.ranking = blog_post.visits * (0.5 + random.random()) / max(3, age.days)

    @api.model
    def create(self, vals):
        if 'content' in vals:
            vals['content'] = self._postproces_content(vals['content'])
        post = super(BlogPost, self.with_context(mail_create_nolog=True)).create(vals)
        post._check_for_publication(vals)
        return post

    @api.multi
    def write(self, vals):
        if 'content' in vals:
            vals['content'] = self._postproces_content(vals['content'])
        result = super(BlogPost, self).write(vals)
        self._check_for_publication(vals)
        return result

    @api.model
    def html_tag_nodes(self, html, attribute=None, tags=None):
        """ Processing of html content to tag paragraphs and set them an unique ID.
            :return result: (html, mapping), where html is the updated html with ID
                    and mapping is a list of (old_ID, new_ID), where old_ID
                    is None if the paragraph is a new one.
        """
        existing_attributes = []
        mapping = []
        if not html:
            return html, mapping
        if tags is None:
            tags = ['p']
        if attribute is None:
            attribute = 'data-unique-id'

        # form a tree
        root = lxml.html.fragment_fromstring(html, create_parent='div')
        if not len(root) and root.text is None and root.tail is None:
            return html, mapping

        # check all nodes, replace :
        # - img src -> check URL
        # - a href -> check URL
        for node in root.iter():
            if node.tag not in tags:
                continue
            ancestor_tags = [parent.tag for parent in node.iterancestors()]

            old_attribute = node.get(attribute)
            new_attribute = old_attribute
            if not new_attribute or (old_attribute in existing_attributes):
                if ancestor_tags:
                    ancestor_tags.pop()
                counter = random.randint(10000, 99999)
                ancestor_tags.append('counter_%s' % counter)
                new_attribute = '/'.join(reversed(ancestor_tags))
                node.set(attribute, new_attribute)

            existing_attributes.append(new_attribute)
            mapping.append((old_attribute, new_attribute))

        html = lxml.html.tostring(root, pretty_print=False, method='html')
        # this is ugly, but lxml/etree tostring want to put everything in a 'div' that breaks the editor -> remove that
        if html.startswith('<div>') and html.endswith('</div>'):
            html = html[5:-6]
        return html, mapping

    @api.multi
    def _postproces_content(self, content):
        # add data-chatter-id on paragraph to allow inline comment
        content, mapping = self.html_tag_nodes(content, attribute='data-chatter-id', tags=['p'])
        # remove mail.messagelink to deleted paragraphs
        if self.ids:  # not creating
            existing = [x[0] for x in mapping if x[0]]
            self.env['mail.message'].sudo().search([
                ('res_id', 'in', self.ids),
                ('model', '=', self._name),
                ('path', 'not in', existing),
                ('path', '!=', False)
            ]).unlink()
        return content

    @api.multi
    def _check_for_publication(self, vals):
        if vals.get('website_published'):
            for post in self:
                post.blog_id.message_post_with_view(
                    'website_blog.blog_post_template_new_post',
                    subject=post.name,
                    values={'post': post},
                    subtype_id=self.env['ir.model.data'].sudo().xmlid_to_res_id('website_blog.mt_blog_blog_published'))
            return True
        return False

    @api.multi
    def get_access_action(self):
        """ Override method that generated the link to access the document. Instead
            of the classic form view, redirect to the post on the website directly
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/blog/%s/post/%s' % (self.blog_id.id, self.id),
            'target': 'self',
            'res_id': self.id,
        }

    @api.multi
    def _notification_get_recipient_groups(self, message, recipients):
        """ Override to set the access button: everyone can see an access button
            on their notification email. It will lead on the website view of the post.
        """
        result = super(BlogPost, self)._notification_get_recipient_groups(message, recipients)
        access_action = self._notification_link_helper('view', model=message.model, res_id=message.res_id)
        for category, data in result.iteritems():
            result[category]['button_access'] = {'url': access_action, 'title': _('View Blog Post')}
        return result


class Website(models.Model):

    _inherit = "website"

    @api.model
    def page_search_dependencies(self, view_id):
        dep = super(Website, self).page_search_dependencies(view_id)

        view = self.env['ir.ui.view'].browse(view_id)
        name = view.key.replace("website.", "")
        fullname = "website.%s" % name

        posts = self.env['blog.post'].search(['|', ('content', 'ilike', '/page/%s' % name), ('content', 'ilike', '/page/%s' % fullname)])
        for post in posts:
            dep.setdefault(_('Blog Post'), []).append({
                'text': _('Blog Post <b>%s</b> seems to have a link to this page !') % post.name,
                'link': post.website_url
            })
        return dep
