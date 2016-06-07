odoo.define('web_tour.Tip', function(require) {
"use strict";

var Widget = require('web.Widget');

return Widget.extend({
    template: "Tip",
    events: {
        mouseenter: "_to_info_mode",
        mouseleave: "_to_bubble_mode",
    },
    init: function(parent, $anchor, info) {
        this._super(parent);
        this.$anchor = $anchor;
        this.info = _.defaults(info, {
            position: "right",
        });
        this.consumed = false;
    },
    start: function() {
        this.init_width = this.$el.innerWidth();
        this.init_height = this.$el.innerHeight();
        this.$tooltip_content = this.$(".o_tooltip_content");
        this._bind_anchor_events();
        this._reposition();
    },
    update: function($anchor) {
        if (!$anchor.is(this.$anchor)) {
            this.$anchor.off();
            this.$anchor = $anchor;
            this._bind_anchor_events();
        }
        this._reposition();
    },
    _reposition: function() {
        if (this.tip_opened) {
            return;
        }
        this.$el.position({
            my: this._get_spaced_inverted_position(this.info.position),
            at: this.info.position,
            of: this.$anchor,
            collision: "fit",
        });
    },
    _bind_anchor_events: function () {
        var self = this;
        this.$anchor.on('mouseenter', this._to_info_mode.bind(this));
        this.$anchor.on('mouseleave', this._to_bubble_mode.bind(this));
        this.$anchor.on(this.$anchor.is('input,textarea') ? 'change' : 'mousedown', function () {
            if (self.consumed) return;
            self.consumed = true;
            self.trigger('tip_consumed');
        });
    },
    _get_spaced_inverted_position: function (position) {
        if (position === "right") return "left+10";
        if (position === "left") return "right-10";
        if (position === "bottom") return "top+10";
        return "bottom-10";
    },
    _to_info_mode: function() {
        if (this.timerOut !== undefined) {
            clearTimeout(this.timerOut);
            this.timerOut = undefined;
            return;
        }

        this.timerIn = setTimeout((function () {
            this.timerIn = undefined;

            var content_width = this.$tooltip_content.outerWidth();
            var content_height = this.$tooltip_content.outerHeight();

            this.tip_opened = true;
            this.$el.addClass("active");
            this.$el.css({
                width: content_width,
                height: content_height,
                "margin-left": (this.info.position === "left" ? -(content_width - this.init_width) : 0),
                "margin-top": (this.info.position === "top" ? -(content_height - this.init_height) : 0),
            });
        }).bind(this), 200);
    },
    _to_bubble_mode: function () {
        if (this.timerIn !== undefined) {
            clearTimeout(this.timerIn);
            this.timerIn = undefined;
            return;
        }

        this.timerOut = setTimeout((function () {
            this.timerOut = undefined;

            this.tip_opened = false;
            this.$el.removeClass("active");
            this.$el.css({
                width: this.init_width,
                height: this.init_height,
                margin: 0,
            });
        }).bind(this), 200);
    },
});
});
