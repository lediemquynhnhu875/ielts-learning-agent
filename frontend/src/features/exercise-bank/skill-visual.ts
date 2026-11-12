import type { ComponentType, SVGProps } from "react";
import { BookIcon, HeadphonesIcon, MicIcon, PenIcon } from "@/components/icons";
import type { Skill } from "@/mock-data/types";

type SkillVisual = {
  icon: ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;
  /** Ô icon nhỏ: nền màu kỹ năng, chữ tương phản (navy trên cam). */
  tile: string;
  /** Ảnh đại diện card: gradient theo màu kỹ năng. */
  thumb: string;
};

export const skillVisual: Record<Skill, SkillVisual> = {
  reading: {
    icon: BookIcon,
    tile: "bg-skill-reading text-cream",
    thumb: "bg-linear-135 from-[#2c4f85] to-navy-deep text-cream",
  },
  listening: {
    icon: HeadphonesIcon,
    tile: "bg-skill-listening text-navy-deep",
    thumb: "bg-linear-135 from-orange-light to-[#e8963f] text-navy-deep",
  },
  writing: {
    icon: PenIcon,
    tile: "bg-skill-writing text-cream",
    thumb: "bg-linear-135 from-[#6c93d3] to-[#3a63a8] text-cream",
  },
  speaking: {
    icon: MicIcon,
    tile: "bg-skill-speaking text-cream",
    thumb: "bg-linear-135 from-[#c06a26] to-[#8a4210] text-cream",
  },
};
