.syntax unified
.arm
.text

.macro save_args
    push {r0-r3, ip, lr}
    mrs r3, apsr
    push {r3, r4}
.endm

.macro restore_args
    pop {r3, r4}
    msr apsr_nzcvq, r3
    pop {r0-r3, ip, lr}
.endm

.macro prologue_hook name, helper, continuation
.global \name
.type \name, %function
\name:
    save_args
    bl \helper
    restore_args
    mov ip, sp
    ldr pc, =\continuation
.size \name, .-\name
.endm

prologue_hook m10v_guides_hook_update, m10v_guides_camera_update, 0x53176820
prologue_hook m10v_guides_hook_prepare, m10v_guides_camera_prepare, 0x53391b18

/* Displaced BL 0x53393d28: enter the original child dispatch once. */
.global m10v_guides_hook_paint
.type m10v_guides_hook_paint, %function
m10v_guides_hook_paint:
    push {r4, lr}
    mov r4, r0
    save_args
    bl m10v_guides_camera_paint
    restore_args
    ldr ip, =0x53393d28
    blx ip
    save_args
    mov r0, r4
    bl m10v_guides_camera_finish
    restore_args
    pop {r4, pc}
.size m10v_guides_hook_paint, .-m10v_guides_hook_paint

.global m10v_guides_hook_grid
.type m10v_guides_hook_grid, %function
m10v_guides_hook_grid:
    save_args
    bl m10v_guides_camera_suppress_grid
    cmp r0, #0
    beq .Lstock_grid
    restore_args
    bx lr
.Lstock_grid:
    restore_args
    mov ip, sp
    ldr pc, =0x5339c3b4
.size m10v_guides_hook_grid, .-m10v_guides_hook_grid
.ltorg
