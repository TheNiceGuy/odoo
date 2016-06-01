odoo.define('web_tour.tour', function(require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var TourManager = require('web_tour.TourManager');

var QWeb = core.qweb;

return $.when($.get('/web_tour/static/src/xml/tip.xml'), session.is_bound).then(function (template) {
    QWeb.add_template(template[0]);
    var tour = new TourManager(session.web_tours);
    var untracked_classnames = ['o_tooltip', 'o_breathing'];

    $(function () {
        var check_tooltip = _.throttle(function (records) {
            var update = _.find(records, function (record) {
                var record_class = record.target.className;
                return !_.isString(record_class) ||
                       _.intersection(record_class.split(' '), untracked_classnames).length === 0;
            });
            if (update) { // ignore mutations in the tooltip itself
                tour.update();
            }
        }, 500, {leading: false});
        var observer = new MutationObserver(check_tooltip);
        observer.observe(document.body, {
            attributes: true,
            childList: true,
            subtree: true,
        });
    });

    return tour;
});

});
