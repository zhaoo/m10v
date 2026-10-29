.syntax unified
.arm
.text
.global border_recovery_transfer_body_hook
.type border_recovery_transfer_body_hook,%function
border_recovery_transfer_body_hook:
 push {r3,lr}
 mov r2,r4
 bl m10v_border_transfer_body
 pop {r3,pc}
.global border_recovery_transfer_wait_hook
.type border_recovery_transfer_wait_hook,%function
border_recovery_transfer_wait_hook:
 push {r4,lr}
 sub sp,sp,#8
 str r5,[sp]
 bl m10v_border_transfer_wait
 add sp,sp,#8
 pop {r4,pc}
.global border_recovery_fill_body_hook
.type border_recovery_fill_body_hook,%function
border_recovery_fill_body_hook:
 push {r3,lr}
 mov r2,r4
 bl m10v_border_fill_body
 pop {r3,pc}
.global border_recovery_resize_body_hook
.type border_recovery_resize_body_hook,%function
border_recovery_resize_body_hook:
 push {r3,lr}
 mov r2,r4
 bl m10v_border_resize_body
 pop {r3,pc}
.global border_recovery_fill_wait_hook
.type border_recovery_fill_wait_hook,%function
border_recovery_fill_wait_hook:
 push {r4,lr}
 sub sp,sp,#8
 str fp,[sp]
 str r6,[sp,#4]
 bl m10v_border_fill_wait
 add sp,sp,#8
 pop {r4,pc}
.global border_recovery_resize_wait_hook
.type border_recovery_resize_wait_hook,%function
border_recovery_resize_wait_hook:
 push {r4,lr}
 sub sp,sp,#8
 str fp,[sp]
 bl m10v_border_resize_wait
 add sp,sp,#8
 pop {r4,pc}
.global border_recovery_resize_dma_wait_hook
.type border_recovery_resize_dma_wait_hook,%function
border_recovery_resize_dma_wait_hook:
 push {r4,lr}
 sub sp,sp,#8
 str r7,[sp]
 bl m10v_border_resize_dma_wait
 add sp,sp,#8
 pop {r4,pc}
.global border_recovery_fill_release_hook
.type border_recovery_fill_release_hook,%function
border_recovery_fill_release_hook:
 push {r4,lr}
 mov r3,fp
 sub sp,sp,#8
 str r6,[sp]
 bl m10v_border_fill_release
 add sp,sp,#8
 pop {r4,pc}
.global border_recovery_resize_release_hook
.type border_recovery_resize_release_hook,%function
border_recovery_resize_release_hook:
 push {r4,lr}
 mov r3,fp
 bl m10v_border_resize_release
 pop {r4,pc}
