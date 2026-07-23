package main

import (
	"encoding/json"
	"net/http"
	"sync"

	"github.com/mattermost/mattermost/server/public/model"
	"github.com/mattermost/mattermost/server/public/plugin"
)

// HookRecorderPlugin is a black-box observability shim for the SaaSBench
// evaluation harness. It implements a representative set of Mattermost plugin
// hooks and records, in-memory, how many times each hook fired and in what
// order. The harness triggers the corresponding server events over the public
// REST API (post a message, add a user to a channel, patch config) and then
// reads back the recorded counters via this plugin's ServeHTTP endpoint,
// turning otherwise-internal Go hook invocations into deterministic black-box
// signals.
type HookRecorderPlugin struct {
	plugin.MattermostPlugin

	mu     sync.Mutex
	counts map[string]int
	order  []string
}

func (p *HookRecorderPlugin) record(hook string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.counts == nil {
		p.counts = map[string]int{}
	}
	p.counts[hook]++
	p.order = append(p.order, hook)
	if len(p.order) > 512 {
		p.order = p.order[len(p.order)-512:]
	}
}

func (p *HookRecorderPlugin) OnActivate() error {
	p.mu.Lock()
	p.counts = map[string]int{}
	p.order = nil
	p.mu.Unlock()
	p.record("OnActivate")
	return nil
}

// OnConfigurationChange fires once before OnActivate and again on every config
// mutation. Hook ID 3.
func (p *HookRecorderPlugin) OnConfigurationChange() error {
	p.record("OnConfigurationChange")
	return nil
}

// MessageWillBePosted fires before a post is committed; returning the post
// unchanged with an empty reason allows it. Hook ID 5.
func (p *HookRecorderPlugin) MessageWillBePosted(c *plugin.Context, post *model.Post) (*model.Post, string) {
	p.record("MessageWillBePosted")
	return post, ""
}

// MessageHasBeenPosted fires after the post is committed. Hook ID 7. Together
// with MessageWillBePosted this exercises the post-create pipeline ordering.
func (p *HookRecorderPlugin) MessageHasBeenPosted(c *plugin.Context, post *model.Post) {
	p.record("MessageHasBeenPosted")
}

// UserHasJoinedChannel fires when a user is added to a channel. Hook ID 9.
func (p *HookRecorderPlugin) UserHasJoinedChannel(c *plugin.Context, channelMember *model.ChannelMember, actor *model.User) {
	p.record("UserHasJoinedChannel")
}

// ServeHTTP exposes the recorded counters. Routes (relative to
// /plugins/com.eval.hookrecorder):
//
//	GET  /counts  -> {"counts": {...}, "order": [...]}
//	POST /reset   -> zero all counters, returns {"reset": true}
func (p *HookRecorderPlugin) ServeHTTP(c *plugin.Context, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	switch r.URL.Path {
	case "/reset":
		p.mu.Lock()
		p.counts = map[string]int{}
		p.order = nil
		p.mu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]any{"reset": true})
	case "/counts":
		p.mu.Lock()
		cp := make(map[string]int, len(p.counts))
		for k, v := range p.counts {
			cp[k] = v
		}
		od := append([]string(nil), p.order...)
		p.mu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]any{"counts": cp, "order": od})
	default:
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(map[string]any{"error": "unknown path", "path": r.URL.Path})
	}
}

func main() {
	plugin.ClientMain(&HookRecorderPlugin{})
}
