import * as React from "react";
import { Button, type ButtonProps } from "@/components/ui/button";

export interface IconButtonProps extends Omit<ButtonProps, "children"> {
  label: string;
  children: React.ReactNode;
}

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ label, title, type = "button", ...props }, ref) => (
    <Button
      ref={ref}
      type={type}
      size="icon"
      aria-label={label}
      title={title || label}
      {...props}
    />
  )
);
IconButton.displayName = "IconButton";
