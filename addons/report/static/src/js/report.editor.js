odoo.define('report.editor', function (require) {
"use strict";

var editor = require('web_editor.editor');
var options = require('web_editor.snippets.options');

var old_save = editor.save;
editor.save = function () {
    old_save.apply(this, arguments);
}

options.registry.many2one.include({
    select_record: function (li) {
        var self = this;
        this._super(li);
        if (this.$target.data('oe-field') === "partner_id") {
            var $img = $('.header .row img:first');
            var css = window.getComputedStyle($img[0]);
            $img.css("max-height", css.height+'px');
            $img.attr("src", "/web/image/res.partner/"+self.ID+"/image");
            setTimeout(function () { $img.removeClass('o_dirty'); },0);
        }
    }
});

window.parent.postMessage("teseeeet", "http://127.0.0.1:8069");

});