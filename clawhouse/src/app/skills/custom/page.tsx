"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SkillTypeBadge } from "@/components/status-badge";

interface SkillData {
  name: string;
  type: "mcp" | "cli";
  status: string;
  description: string;
  emoji?: string;
  allowed_tools?: string[];
  environment_variables?: string[];
  required_commands?: string[];
  usedBy: string[];
  isBuiltin?: boolean;
}

interface SkillDetail {
  config: SkillData | null;
  skillMarkdown: string;
}

export default function CustomSkillsPage() {
  const [skills, setSkills] = useState<SkillData[]>([]);
  const [editingSkill, setEditingSkill] = useState<string | null>(null);
  const [editConfig, setEditConfig] = useState<Partial<SkillData>>({});
  const [editMarkdown, setEditMarkdown] = useState("");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newMarkdown, setNewMarkdown] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchSkills = () => {
    fetch("/api/skills")
      .then((r) => r.json())
      .then((data) => {
        setSkills((data || []).filter((s: SkillData) => !s.isBuiltin));
      });
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const handleEdit = async (name: string) => {
    const response = await fetch(`/api/skills/${name}`);
    const detail: SkillDetail = await response.json();
    if (detail.config) {
      setEditConfig(detail.config);
      setEditMarkdown(detail.skillMarkdown || "");
      setEditingSkill(name);
    }
  };

  const handleSaveEdit = async () => {
    if (!editingSkill) return;
    setSaving(true);
    await fetch(`/api/skills/${editingSkill}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: editConfig, skillMarkdown: editMarkdown }),
    });
    setSaving(false);
    setEditingSkill(null);
    fetchSkills();
  };

  const handleDelete = async (name: string) => {
    if (!window.confirm(`Delete skill "${name}"?`)) return;
    await fetch(`/api/skills/${name}`, { method: "DELETE" });
    fetchSkills();
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setSaving(true);
    await fetch("/api/skills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName.trim(),
        config: { description: newDescription },
        skillMarkdown: newMarkdown,
      }),
    });
    setSaving(false);
    setAdding(false);
    setNewName("");
    setNewDescription("");
    setNewMarkdown("");
    fetchSkills();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Custom Skills</h1>
          <p className="text-muted-foreground text-sm">
            {skills.length} user-created skill{skills.length !== 1 ? "s" : ""}{" "}
            in ~/.cclaw/skills/
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setAdding(!adding)}>
          {adding ? "Cancel" : "Add Skill"}
        </Button>
      </div>

      {adding && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">New Skill</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Name</Label>
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="my-skill"
                />
              </div>
              <div className="space-y-2">
                <Label>Description</Label>
                <Input
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="What this skill does"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>SKILL.md</Label>
              <Textarea
                rows={6}
                value={newMarkdown}
                onChange={(e) => setNewMarkdown(e.target.value)}
                placeholder="# My Skill&#10;&#10;Instructions for Claude..."
                className="font-mono text-sm"
              />
            </div>
            <Button size="sm" onClick={handleCreate} disabled={saving}>
              {saving ? "Creating..." : "Create"}
            </Button>
          </CardContent>
        </Card>
      )}

      {skills.length === 0 && !adding ? (
        <p className="text-sm text-muted-foreground">No custom skills found.</p>
      ) : (
        <div className="space-y-4">
          {skills.map((skill) =>
            editingSkill === skill.name ? (
              <Card key={skill.name}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{skill.name}</CardTitle>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingSkill(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveEdit}
                        disabled={saving}
                      >
                        {saving ? "Saving..." : "Save"}
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Description</Label>
                      <Input
                        value={editConfig.description || ""}
                        onChange={(e) =>
                          setEditConfig({
                            ...editConfig,
                            description: e.target.value,
                          })
                        }
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Emoji</Label>
                      <Input
                        value={editConfig.emoji || ""}
                        onChange={(e) =>
                          setEditConfig({
                            ...editConfig,
                            emoji: e.target.value || undefined,
                          })
                        }
                        placeholder="🔧"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>SKILL.md</Label>
                    <Textarea
                      rows={10}
                      value={editMarkdown}
                      onChange={(e) => setEditMarkdown(e.target.value)}
                      className="font-mono text-sm"
                    />
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card key={skill.name} id={skill.name}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">
                      {skill.emoji && `${skill.emoji} `}
                      {skill.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <SkillTypeBadge type={skill.type} />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleEdit(skill.name)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDelete(skill.name)}
                        className="text-destructive"
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  <CardDescription className="text-xs">
                    {skill.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {skill.usedBy?.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">
                        Used by
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {skill.usedBy.map((botName) => (
                          <Badge
                            key={botName}
                            variant="secondary"
                            className="text-xs"
                          >
                            {botName}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {skill.allowed_tools && skill.allowed_tools.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">
                        Tools ({skill.allowed_tools.length})
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {skill.allowed_tools.slice(0, 5).map((tool) => (
                          <Badge
                            key={tool}
                            variant="outline"
                            className="text-xs font-mono"
                          >
                            {tool.length > 30
                              ? tool.substring(0, 30) + "..."
                              : tool}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {skill.required_commands &&
                    skill.required_commands.length > 0 && (
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">
                          Requires
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {skill.required_commands.map((cmd) => (
                            <Badge
                              key={cmd}
                              variant="outline"
                              className="text-xs font-mono"
                            >
                              {cmd}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                </CardContent>
              </Card>
            ),
          )}
        </div>
      )}
    </div>
  );
}
